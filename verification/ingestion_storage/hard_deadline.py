"""A hard, client-side deadline for a blocking database call that does not depend on any server-side timeout.

Server timeouts (statement_timeout, lock_timeout) are requested through startup options. A pooler may ignore those options, and a diagnostic connection can succeed without them, so
they cannot be the only deadline. This helper bounds the CLIENT side: a watchdog thread sends a signal to the main thread, whose handler raises `DeadlineExceeded` out of the blocked
call (psycopg waits in Python-visible poll/select, so the signal interrupts it). The caller then cancels and closes the connection (`abandon`).

It does not use SIGALRM, so it never disturbs the session controller's one-shot work alarm, and the existing `HardDeadline` (a watcher thread that exits the process) remains the outer
backstop for anything that cannot be interrupted (for example a hang inside connection establishment, which `connect_timeout` bounds instead). It is NOT a substitute for a
server-side timeout where one is reflected; it is the independent second control. Contexts do not nest: a nested use is refused rather than silently discarding the outer deadline.
"""
import signal,threading
from contextlib import contextmanager

SIGNAL=signal.SIGUSR1
_active=threading.Lock()


class DeadlineExceeded(RuntimeError):
    """The fixed code is the whole message."""
    def __init__(self,code):
        self.code=code;super().__init__(code)


@contextmanager
def hard_deadline(seconds,code):
    if threading.current_thread() is not threading.main_thread():raise RuntimeError('HARD_DEADLINE_MAIN_THREAD_ONLY')
    if not 0<seconds<=3600:raise ValueError('HARD_DEADLINE_BOUND')
    if not _active.acquire(blocking=False):raise RuntimeError('HARD_DEADLINE_NESTED')
    try:                                          # the lock is released on EVERY exit path, including a failure while installing the handler or starting the watchdog
        main=threading.get_ident();done=threading.Event();live=[True];state=dict(previous=signal.SIG_DFL,installed=False,thread=None)
        def handler(signum,frame):
            if live[0]:raise DeadlineExceeded(code)      # a signal that raced the normal exit is ignored, never raised after the call has completed
        def watch():
            if not done.wait(seconds) and live[0]:
                try:signal.pthread_kill(main,SIGNAL)
                except Exception:pass
        try:
            state['previous']=signal.signal(SIGNAL,handler);state['installed']=True
            state['thread']=threading.Thread(target=watch,name='hard-deadline',daemon=True);state['thread'].start()
            yield
        finally:
            try:live[0]=False                     # a signal can still land on this very line; it is swallowed so teardown always completes
            except DeadlineExceeded:live[0]=False
            mask=signal.pthread_sigmask(signal.SIG_BLOCK,{SIGNAL})
            try:
                done.set()
                if state['installed']:
                    signal.signal(SIGNAL,signal.SIG_IGN)          # discards any pending signal
                    if state['thread'] is not None:state['thread'].join(timeout=1)
                    late=state['thread'] is not None and state['thread'].is_alive()      # a watchdog that outlived the join must never meet the default (fatal) disposition
                    signal.signal(SIGNAL,signal.SIG_IGN if late else (state['previous'] if state['previous'] is not None else signal.SIG_DFL))
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK,mask)
    finally:
        _active.release()


CANCEL_TIMEOUT_SECONDS=2.0
CLOSE_ALLOWANCE_SECONDS=1.0
OUTCOMES=('CANCEL_SENT','CANCEL_FAILED_TIMEOUT','CANCEL_FAILED','CANCEL_SKIPPED_NOT_BOUNDABLE','CANCEL_SKIPPED_NO_CONNECTION')


def abandon(connection,*,clock=None):
    """After a deadline: ask the server to CANCEL the running statement, then close the client side. Every step is bounded and ACCOUNTED.

    What `cancel_safe` really does (psycopg 3.3, libpq >= 17): it opens a SEPARATE cancel connection to the server's address (TLS as configured) that sends a cancel request. It is not a
    login: it does not authenticate as the role and does not count against the role's CONNECTION LIMIT, but it is a real network connection that can itself stall, which is why it carries
    its own timeout. With libpq < 17 `cancel_safe` would fall back to a blocking `cancel()` with no timeout; that path is never taken here (outcome CANCEL_SKIPPED_NOT_BOUNDABLE).
    A cancel request being SENT or acknowledged is not evidence that the statement stopped, and the backend's closure is never claimed here: `backend_closure` is always NOT_ESTABLISHED
    and only a later session readback can establish it. Closing alone does not end a running backend (tested)."""
    import time
    clock=clock or time.monotonic
    outcome='CANCEL_SKIPPED_NO_CONNECTION';cancel_seconds=0.0
    if connection is not None:
        began=clock()
        try:
            from psycopg import capabilities,errors
            if not capabilities.has_cancel_safe():outcome='CANCEL_SKIPPED_NOT_BOUNDABLE'
            else:
                try:
                    connection.cancel_safe(timeout=CANCEL_TIMEOUT_SECONDS);outcome='CANCEL_SENT'
                except errors.CancellationTimeout:outcome='CANCEL_FAILED_TIMEOUT'
        except BaseException:
            outcome='CANCEL_FAILED'
        cancel_seconds=clock()-began
    began=clock()
    try:
        if connection is not None:connection.close()
    except BaseException:pass
    close_seconds=clock()-began
    return dict(cancel_requested=outcome=='CANCEL_SENT',cancel_outcome=outcome,cancel_attempts=0 if outcome.startswith('CANCEL_SKIPPED') else 1,cancel_seconds=round(cancel_seconds,3),
                client_closed=bool(getattr(connection,'closed',False)) if connection is not None else None,close_seconds=round(close_seconds,3),backend_closure='NOT_ESTABLISHED')
