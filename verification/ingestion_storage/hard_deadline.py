"""A hard, client-side deadline for a blocking database call that does not depend on any server-side timeout.

Server timeouts (statement_timeout, lock_timeout) are requested through startup options. A pooler may ignore those options, and a diagnostic connection can succeed without them, so
they cannot be the only deadline. This helper bounds the CLIENT side: a watchdog thread sends a signal to the main thread, whose handler raises `DeadlineExceeded` out of the blocked
call (psycopg waits in Python-visible poll/select, so the signal interrupts it). The caller then closes the connection, which ends the server backend when the socket closes.

It does not use SIGALRM, so it never disturbs the session controller's one-shot work alarm, and the existing `HardDeadline` (a watcher thread that exits the process) remains the outer
backstop for anything that cannot be interrupted. It is NOT an accepted substitute for a server-side timeout where one is reflected; it is the independent second control.
"""
import signal,threading
from contextlib import contextmanager

SIGNAL=signal.SIGUSR1


class DeadlineExceeded(RuntimeError):
    """The fixed code is the whole message."""
    def __init__(self,code):
        self.code=code;super().__init__(code)


@contextmanager
def hard_deadline(seconds,code):
    if threading.current_thread() is not threading.main_thread():raise RuntimeError('HARD_DEADLINE_MAIN_THREAD_ONLY')
    if not 0<seconds<=3600:raise ValueError('HARD_DEADLINE_BOUND')
    main=threading.get_ident();done=threading.Event();fired=threading.Event()
    def handler(signum,frame):raise DeadlineExceeded(code)
    previous=signal.signal(SIGNAL,handler)
    def watch():
        if not done.wait(seconds):
            fired.set()
            try:signal.pthread_kill(main,SIGNAL)
            except Exception:pass
    thread=threading.Thread(target=watch,name='hard-deadline',daemon=True);thread.start()
    try:
        yield
    finally:
        done.set()
        signal.signal(SIGNAL,signal.SIG_IGN)       # a signal that raced the normal exit is discarded rather than raised later
        thread.join(timeout=1)
        signal.signal(SIGNAL,previous if previous is not None else signal.SIG_DFL)


def abandon(connection):
    """After a deadline: ask the server to CANCEL the running statement over a separate, time-bounded cancel connection, then close the client side.

    Closing alone is NOT enough: a backend running a long statement does not notice the client has gone until the statement ends (client_connection_check_interval is off by default),
    and a pooler may or may not forward a cancel. So this reports what was done, never that the backend has ended; the session readback in teardown remains the only proof."""
    sent=False
    try:
        connection.cancel_safe(timeout=2.0);sent=True
    except BaseException:
        pass
    try:connection.close()
    except BaseException:pass
    return dict(cancel_requested=sent,client_closed=bool(getattr(connection,'closed',False)))
