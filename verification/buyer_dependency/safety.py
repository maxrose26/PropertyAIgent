"""Dedicated observation boundary. No product imports or production activation.

Python audit hooks constrain the reviewed Python call path, not arbitrary native
code. Run in a dedicated process; no preloaded model clients are permitted.
"""
from contextlib import contextmanager
import builtins
import signal
import sys
import time
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Select
from verification.gate_b.safety import ReadOnlyViolation, is_allowed_statement

class ObservationFailure(RuntimeError):
    pass

@contextmanager
def guarded_window(session, *, synthetic=False, max_queries=12000, seconds=120):
    if session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ObservationFailure("fresh session required")
    engine = session.get_bind()
    if engine.dialect.name != ("sqlite" if synthetic else "postgresql"):
        raise ObservationFailure("backend mismatch")
    if any(m.split('.')[0] in {'openai','anthropic'} for m in sys.modules):
        raise ObservationFailure("model module preloaded")
    state = dict(queries=0, snapshot=None, isolation=None, synthetic=synthetic)
    active = [True]
    def audit(name, args):
        if active[0] and (name.startswith('socket.') or name in {'subprocess.Popen','os.system','os.posix_spawn'}):
            raise ObservationFailure("external execution/network denied")
    sys.addaudithook(audit)
    old_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name.split('.')[0] in {'openai','anthropic'}:
            raise ObservationFailure("model import denied")
        return old_import(name, *args, **kwargs)
    builtins.__import__ = guarded_import
    started = time.monotonic()
    beginnings = [0]
    controls = {'SHOW transaction_read_only','SHOW transaction_isolation','SELECT pg_current_snapshot()::text'}
    def count(conn,cursor,statement,parameters,context,executemany):
        state['queries'] += 1
        if state['queries'] > max_queries or time.monotonic()-started > seconds:
            raise ObservationFailure("query/runtime overflow")
        if not is_allowed_statement(statement) and not statement.upper().startswith(('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY','SET LOCAL LOCK_TIMEOUT')):
            raise ReadOnlyViolation("SQL rejected")
        # Only reviewed ORM SELECTs or the exact safety controls. Textual SELECT
        # functions/procedures supplied by consumers are not admitted.
        if statement not in controls and statement.lstrip().upper().startswith(('SELECT','WITH')):
            if not isinstance(getattr(context,'compiled',None).statement if getattr(context,'compiled',None) else None, Select):
                raise ReadOnlyViolation("unreviewed SQL text rejected")
    def begin(sess, transaction, connection):
        if sess is not session or beginnings[0]:
            raise ObservationFailure("uncontrolled/replacement transaction")
        beginnings[0] += 1
        if not synthetic:
            connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
            connection.execute(text("SET LOCAL statement_timeout = '5s'"))
            connection.execute(text("SET LOCAL lock_timeout = '2s'"))
    def reject(*args):
        raise ReadOnlyViolation("flush/commit rejected")
    def deadline(*args):
        raise ObservationFailure("runtime timeout")
    old_signal = signal.signal(signal.SIGALRM,deadline)
    old_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    listeners=[(engine,'before_cursor_execute',count),(Session,'after_begin',begin),(session,'before_flush',reject),(session,'before_commit',reject)]
    for target,name,fn in listeners: event.listen(target,name,fn)
    try:
        session.connection()
        if not synthetic:
            if session.execute(text('SHOW transaction_read_only')).scalar() != 'on': raise ObservationFailure('not read only')
            state['isolation']=session.execute(text('SHOW transaction_isolation')).scalar()
            if state['isolation'] != 'repeatable read': raise ObservationFailure('wrong isolation')
            state['snapshot']=session.execute(text('SELECT pg_current_snapshot()::text')).scalar()
        else:
            state['snapshot']='SYNTHETIC_NOT_POSTGRESQL'; state['isolation']='SYNTHETIC'
        yield state
        if not session.in_transaction(): raise ObservationFailure('transaction lost')
        if not synthetic and session.execute(text('SELECT pg_current_snapshot()::text')).scalar()!=state['snapshot']:
            raise ObservationFailure('snapshot changed')
    finally:
        active[0]=False
        builtins.__import__=old_import
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,old_signal)
        if old_timer[0]: signal.setitimer(signal.ITIMER_REAL,*old_timer)
        try: session.rollback()
        finally:
            for target,name,fn in reversed(listeners): event.remove(target,name,fn)
            session.close()
