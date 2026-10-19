"""The operational runtime connection path (DatabaseBudget): a client-side hard deadline on every driver call, plus the existing fail-closed qualification of the EFFECTIVE server timeouts.

Real blocked query on a disposable server. Two independent controls: (1) the creator refuses a connection whose session does not carry the reviewed server timeouts; (2) when the server
settings ARE reflected, a blocked call is still bounded on the client and the server backend is cancelled."""
import time
import psycopg,pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from app.ingestion.ledger import Denied
from verification.ingestion_storage import operational_controller as oc
from verification.ingestion_storage.operational_controller import DatabaseBudget
from tests.test_ingestion_admin_connection_probe import cluster      # noqa: F401
from tests.test_ingestion_restricted_matrix import roles,WORKER,sessions      # noqa: F401


@pytest.fixture
def local_principal(monkeypatch,cluster):
    monkeypatch.setattr(oc,'runtime_principal',lambda url,ssl:(make_url(url),make_url(url).username))
    return f'postgresql+psycopg://{WORKER}:synthetic@127.0.0.1:{cluster.port}/postgres'


def backend_count(cluster,pid):
    with psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user='postgres',autocommit=True) as c:
        return c.execute('SELECT count(*) FROM pg_stat_activity WHERE pid=%s',(pid,)).fetchone()[0]


def test_normal_statements_are_unaffected_and_accounted_as_before(cluster,roles,local_principal):
    budget=DatabaseBudget();engine=budget.engine(local_principal)
    with engine.connect() as c:assert c.execute(text('SELECT 1')).scalar()==1
    account=budget.close([])
    assert account['cleanup']=='CLOSED' and account['hard_deadline_events']==[] and account['connection_attempts']==1 and account['driver_statements']>=2


def test_a_blocked_runtime_statement_is_interrupted_cancelled_and_denied(cluster,roles,local_principal,monkeypatch):
    monkeypatch.setattr(oc,'STATEMENT_HARD_SECONDS',1)
    budget=DatabaseBudget();engine=budget.engine(local_principal)
    with engine.connect() as c:
        pid=c.connection.driver_connection.info.backend_pid
        started=time.monotonic()
        with pytest.raises(Exception) as caught:c.execute(text('SELECT pg_sleep(30)'))
        elapsed=time.monotonic()-started
    assert 'STATEMENT_HARD_DEADLINE' in repr(caught.value) and 0.9<=elapsed<4.0                      # bounded by the client deadline, not the 30 s statement and not the 10 s server timeout
    deadline=time.monotonic()+5
    while backend_count(cluster,pid) and time.monotonic()<deadline:time.sleep(.1)
    assert backend_count(cluster,pid)==0                                                              # the server backend was cancelled and ended
    account=budget.close([])
    assert len(account['hard_deadline_events'])>=1 and account['hard_deadline_events'][0]['cancel_requested'] is True and account['cleanup']=='CLOSED' and account['connections_closed'] is True
    assert sessions(cluster)==0


def test_ignored_server_timeouts_fail_the_qualification_before_any_statement(cluster,roles,local_principal,monkeypatch):
    real=psycopg.Connection.connect.__func__
    seen=[]
    def stripped(cls,conninfo='',**kw):
        seen.append(kw.pop('options',None));return real(cls,conninfo,**kw)                          # the transport ignores the startup options
    monkeypatch.setattr(psycopg.Connection,'connect',classmethod(stripped))
    budget=DatabaseBudget();engine=budget.engine(local_principal)
    with pytest.raises(Exception) as caught:
        with engine.connect() as c:c.execute(text('SELECT 1'))
    assert 'SERVER_TIMEOUT_OR_RESTRICTED_IDENTITY_PROFILE' in repr(caught.value) and seen and seen[0]                  # options were requested ...
    account=budget.close([]);assert account['cleanup']=='CLOSED' and sessions(cluster)==0                 # ... but a session that does not carry them is refused and closed
    assert account['connection_diagnostics'][-1]['phase']=='SERVER_IDENTITY' and account['connection_diagnostics'][-1]['role']==WORKER


def test_the_client_ceiling_is_strictly_above_the_server_timeout():
    assert oc.STATEMENT_HARD_SECONDS>10             # the 10 s server statement_timeout stays the primary control whenever the transport reflects it



# --- a stalled COMMIT/ROLLBACK is bounded too (these waits are not cursor statements) --------------------------------------------------------------------------

import socket,threading


class StallingProxy:
    """TCP forwarder to the disposable server that can be told to stop forwarding in both directions (a stalled socket / ignoring pooler)."""
    def __init__(self,port):
        self.target=port;self.stall=threading.Event();self.server=socket.socket();self.server.bind(('127.0.0.1',0));self.server.listen(8);self.port=self.server.getsockname()[1];self.alive=True
        threading.Thread(target=self.accept,daemon=True).start()
    def accept(self):
        while self.alive:
            try:client,_=self.server.accept()
            except OSError:return
            upstream=socket.create_connection(('127.0.0.1',self.target))
            for a,b in ((client,upstream),(upstream,client)):threading.Thread(target=self.pump,args=(a,b),daemon=True).start()
    def pump(self,src,dst):
        try:
            while self.alive:
                data=src.recv(65536)
                if not data:break
                while self.stall.is_set() and self.alive:time.sleep(.05)       # hold the bytes: nothing reaches the other side
                dst.sendall(data)
        except OSError:pass
        finally:
            for x in (src,dst):
                try:x.close()
                except OSError:pass
    def close(self):
        self.alive=False
        try:self.server.close()
        except OSError:pass


def test_a_stalled_commit_is_bounded_by_the_client_deadline(cluster,roles,monkeypatch):
    monkeypatch.setattr(oc,'runtime_principal',lambda url,ssl:(make_url(url),make_url(url).username))
    monkeypatch.setattr(oc,'STATEMENT_HARD_SECONDS',1)
    proxy=StallingProxy(cluster.port);url=f'postgresql+psycopg://ingestion_effect_login:synthetic@127.0.0.1:{proxy.port}/postgres'
    budget=DatabaseBudget();engine=budget.engine(url)                          # the effect login runs in a normal (non-autocommit) transaction
    try:
        c=engine.connect();c.execute(text('SELECT 1'))
        proxy.stall.set()
        started=time.monotonic()
        with pytest.raises(Exception) as caught:c.commit()
        elapsed=time.monotonic()-started
        assert 'STATEMENT_HARD_DEADLINE' in repr(caught.value) and 0.9<=elapsed<4.0 and len(budget.hard_deadline_events)>=1
        proxy.stall.clear()
    finally:
        try:c.close()
        except Exception:pass
        account=budget.close([]);proxy.close()
    assert account['connections_closed'] is True and account['cleanup']=='CLOSED'
