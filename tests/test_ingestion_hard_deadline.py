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
    assert outcome=={'cancel_requested':True,'client_closed':True} and c.closed and not backends(cluster,pid)      # cancel + close ends the backend


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
