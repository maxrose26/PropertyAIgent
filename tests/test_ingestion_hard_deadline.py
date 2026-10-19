"""The client-side hard deadline against a REAL blocked query on a server with NO statement timeout (the case where startup options are ignored by a pooler).

An elapsed-time check after a blocking call returns would prove nothing here: pg_sleep(30) does not return. The deadline must interrupt it."""
import os,signal,threading,time
import psycopg,pytest
from verification.ingestion_storage.hard_deadline import hard_deadline,DeadlineExceeded,abandon
from tests.test_ingestion_admin_connection_probe import cluster      # noqa: F401


def connect(cluster):return psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user='postgres',autocommit=True,prepare_threshold=None)


def backends(cluster,pid):
    with connect(cluster) as c:return bool(c.execute('SELECT 1 FROM pg_stat_activity WHERE pid=%s',(pid,)).fetchone())


def test_a_blocked_query_is_interrupted_without_any_server_timeout(cluster):
    c=connect(cluster);pid=c.info.backend_pid
    assert c.execute('SHOW statement_timeout').fetchone()==('0',)                       # NO server-side deadline exists
    started=time.monotonic()
    with pytest.raises(DeadlineExceeded) as caught:
        with hard_deadline(1.0,'ENTRY_DEADLINE_EXCEEDED'):c.execute('SELECT pg_sleep(30)')
    elapsed=time.monotonic()-started
    assert caught.value.code=='ENTRY_DEADLINE_EXCEEDED' and 0.9<=elapsed<3.0           # interrupted near the deadline, nowhere near 30 s
    assert backends(cluster,pid)                                                       # the server is still running that query
    outcome=abandon(c);deadline=time.monotonic()+5
    while backends(cluster,pid) and time.monotonic()<deadline:time.sleep(.1)
    assert outcome['cancel_outcome']=='CANCEL_SENT' and outcome['cancel_attempts']==1 and outcome['client_closed'] is True and outcome['backend_closure']=='NOT_ESTABLISHED' and outcome['cancel_seconds']<2.5
    assert c.closed and not backends(cluster,pid)      # the cancel + close ended the backend (the helper itself never claims that)


def test_closing_alone_leaves_a_running_backend_which_is_why_cancel_is_sent_first(cluster):
    c=connect(cluster);pid=c.info.backend_pid
    with pytest.raises(DeadlineExceeded):
        with hard_deadline(.5,'X'):c.execute('SELECT pg_sleep(30)')
    c.close();time.sleep(2)
    try:assert backends(cluster,pid)                                                    # the backend keeps running a statement whose client is gone
    finally:
        with connect(cluster) as admin:admin.execute('SELECT pg_cancel_backend(%s)',(pid,))     # test hygiene only


def test_a_fast_call_is_untouched_and_the_signal_state_is_restored(cluster):
    before=signal.getsignal(signal.SIGUSR1)
    c=connect(cluster)
    with hard_deadline(5.0,'X'):assert c.execute('SELECT 1').fetchone()==(1,)
    assert signal.getsignal(signal.SIGUSR1)==before
    time.sleep(.2);c.execute('SELECT 2');c.close()                                       # no late signal fires after the context exits


def test_sigalrm_of_the_session_controller_is_not_disturbed(cluster):
    class Alarm(Exception):pass
    def alarm(*_):raise Alarm()
    old=signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,2.5)
    try:
        c=connect(cluster)
        with pytest.raises(DeadlineExceeded):
            with hard_deadline(.5,'D'):c.execute('SELECT pg_sleep(30)')
        c.close()
        with pytest.raises(Alarm):time.sleep(5)                                          # the one-shot session alarm still fires on schedule
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)


def test_main_thread_only_and_bounded():
    errors=[]
    def run():
        try:
            with hard_deadline(1,'X'):pass
        except RuntimeError as e:errors.append(str(e))
    t=threading.Thread(target=run);t.start();t.join()
    assert errors==['HARD_DEADLINE_MAIN_THREAD_ONLY']
    for bad in (0,-1,7200):
        with pytest.raises(ValueError):
            with hard_deadline(bad,'X'):pass


def test_nested_blocked_connect_style_wait_is_also_interrupted(cluster):
    """A query blocked behind a lock (no server lock_timeout) is interrupted the same way."""
    holder=connect(cluster);holder.execute('DROP TABLE IF EXISTS hd_lock');holder.execute('CREATE TABLE hd_lock(i int)');holder.execute('BEGIN');holder.execute('LOCK TABLE hd_lock IN ACCESS EXCLUSIVE MODE')
    waiter=connect(cluster);pid=waiter.info.backend_pid
    try:
        started=time.monotonic()
        with pytest.raises(DeadlineExceeded):
            with hard_deadline(1.0,'LOCK_WAIT'):waiter.execute('SELECT * FROM hd_lock')
        assert time.monotonic()-started<3.0
    finally:
        waiter.close();holder.execute('ROLLBACK');holder.execute('DROP TABLE hd_lock');holder.close()


def test_the_guard_is_released_even_if_teardown_or_setup_fails(monkeypatch):
    real=signal.pthread_sigmask;calls=[]
    def failing(how,mask):
        calls.append(how)
        if len(calls)==1 and how==signal.SIG_BLOCK:raise OSError('injected')
        return real(how,mask)
    monkeypatch.setattr(signal,'pthread_sigmask',failing)
    with pytest.raises(OSError):
        with hard_deadline(5,'X'):pass
    monkeypatch.undo()
    with hard_deadline(5,'AGAIN'):pass                                               # not left locked ("NESTED") by the failure
    def boom(*a,**k):raise OSError('install failed')
    monkeypatch.setattr(signal,'signal',boom)
    with pytest.raises(OSError):
        with hard_deadline(5,'X'):pass
    monkeypatch.undo()
    with hard_deadline(5,'AFTER_SETUP_FAILURE'):pass


def test_a_failed_cancellation_is_recorded_and_the_connection_is_still_closed(cluster,monkeypatch):
    c=connect(cluster);pid=c.info.backend_pid
    monkeypatch.setattr(type(c),'cancel_safe',lambda self,timeout=2.0:(_ for _ in ()).throw(psycopg.OperationalError('cancel failed')))
    outcome=abandon(c)
    assert outcome['cancel_outcome']=='CANCEL_FAILED' and outcome['cancel_requested'] is False and outcome['cancel_attempts']==1 and outcome['client_closed'] is True and outcome['backend_closure']=='NOT_ESTABLISHED'


def test_a_cancel_that_cannot_reach_the_server_is_bounded_by_its_own_timeout(cluster):
    from tests.test_ingestion_statement_deadline import StallingProxy
    proxy=StallingProxy(cluster.port)
    c=psycopg.connect(host='127.0.0.1',port=proxy.port,dbname='postgres',user='postgres',autocommit=True)
    try:
        proxy.stall.set()                                                                    # the cancel connection (and everything else) goes nowhere
        started=time.monotonic();outcome=abandon(c);elapsed=time.monotonic()-started
        assert outcome['cancel_outcome'] in ('CANCEL_FAILED_TIMEOUT','CANCEL_FAILED') and 1.5<=elapsed<4.5 and outcome['client_closed'] is True and outcome['cancel_attempts']==1
        assert outcome['cancel_seconds']<=3.0 and outcome['close_seconds']<1.0
    finally:
        proxy.stall.clear();proxy.close()


def test_without_a_boundable_cancel_none_is_attempted(cluster,monkeypatch):
    from psycopg import capabilities
    monkeypatch.setattr(capabilities,'has_cancel_safe',lambda:False)
    c=connect(cluster);called=[]
    monkeypatch.setattr(type(c),'cancel',lambda self:called.append(1))
    outcome=abandon(c)
    assert outcome['cancel_outcome']=='CANCEL_SKIPPED_NOT_BOUNDABLE' and outcome['cancel_attempts']==0 and not called and outcome['client_closed'] is True        # the unbounded blocking cancel() is never used


def test_abandon_without_a_connection_is_a_recorded_no_op():
    assert abandon(None)['cancel_outcome']=='CANCEL_SKIPPED_NO_CONNECTION'
