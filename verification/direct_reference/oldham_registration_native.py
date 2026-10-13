"""Disposable PostgreSQL wrapper tests; no production credential/source access."""
import os
import resource
from unittest.mock import patch
from sqlalchemy import create_engine,event,select,text,update
from sqlalchemy.orm import Session
from app.db.models import Application
from . import oldham_production as p
from .fixtures import Session as Source,summary
from .persistence_native import seed,read

SCENARIOS=('material','unchanged','withheld','wrong_reference','redirect','audit_rollback','lost_ack','readback_unknown','sql_denial','other_application')
SHA='a'*40

def run_case(engine,monkeypatch,case):
    seed(engine);before=read(engine,42);body=summary(p.REFERENCE,status='Decided',decision='Refuse Permission',date='Fri 25 Sep 2026')
    factory=lambda:Source(body)
    if case=='withheld':factory=lambda:Source(summary(p.REFERENCE,status='Deposited',omit=('Decision','Decision Issued Date')))
    if case=='wrong_reference':factory=lambda:Source(summary('WRONG'))
    if case=='redirect':factory=lambda:Source(body,status=302)
    if case=='audit_rollback':
        def deny(*a):raise ValueError('AUDIT_REJECTED')
        monkeypatch.setattr(p,'check_consequences',deny)
    if case=='lost_ack':
        original=Session.commit
        def lost(s):original(s);raise RuntimeError('lost acknowledgement')
        monkeypatch.setattr(Session,'commit',lost)
    if case=='readback_unknown':
        original=p.snapshot;calls=[]
        def broken(s):
            calls.append(1)
            if len(calls)==3:raise RuntimeError('disposable readback failure')
            return original(s)
        monkeypatch.setattr(p,'snapshot',broken)
    if case=='sql_denial':
        guard=p.install_guards(engine)
        try:
            for q in (text('CREATE TABLE forbidden(id int)'),update(Application).where(Application.id==42).values(status='BAD')):
                try:
                    with engine.begin() as c:c.execute(q)
                except ValueError:pass
                else:raise AssertionError('Unowned SQL admitted')
        finally:event.remove(engine,'before_execute',guard)
        assert read(engine,42)==before;return
    if case=='other_application':
        S=p.session_type()
        with S(engine) as s:assert s.scalars(select(Application).where(Application.id==202)).all()==[]
        return
    out=p.run_transaction(engine,SHA,'123',factory)
    if case in ('material','lost_ack','unchanged'):
        assert out['transaction']=='COMMITTED',out
        assert out['after']['facts']['decision']=='Refuse Permission' and len(out['after']['events'])==1
        assert out['error'] is None
        if case=='lost_ack':assert out['b2_outcome']=='PERSISTENCE_FAILED'
        if case=='unchanged':
            again=p.run_transaction(engine,SHA,'123',factory)
            assert again['transaction']=='COMMITTED' and again['materiality']=='UNCHANGED'
            assert again['after']['events']==out['after']['events']
    elif case=='readback_unknown':
        assert out['transaction']=='UNKNOWN' and out['error']=='COMMIT_ACK_UNKNOWN'
        assert len(read(engine,42)['events'])==1
    else:
        assert out['transaction']=='NOT_COMMITTED',out
        assert read(engine,42)==before
    p.validate(out)
    print('OLDHAM_REGISTRATION_NATIVE_PASS',case)


def resource_worker():
    assert os.environ.get('B20_DISPOSABLE')=='YES_SYNTHETIC_ONLY' and not os.environ.get('DATABASE_URL')
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024));resource.setrlimit(resource.RLIMIT_CPU,(30,30))
    port=int(os.environ['B20_POSTGRES_PORT']);assert 1024<=port<=65535
    engine=create_engine(f'postgresql+psycopg://b20_disposable:b20-disposable-only@127.0.0.1:{port}/b20_disposable',pool_size=1,max_overflow=0,connect_args={'connect_timeout':5,'options':'-c statement_timeout=10000 -c lock_timeout=8000'})
    try:
        out=p.run_transaction(engine,SHA,'123',lambda:Source(summary(p.REFERENCE,status='Decided',decision='Refuse Permission',date='Fri 25 Sep 2026')))
        assert out['transaction']=='COMMITTED',out
        assert engine.pool.checkedout()==0
        print('OLDHAM_NATIVE_RESOURCE_PASS peak_rss_kib',resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    finally:engine.dispose()

if __name__=='__main__':resource_worker()
