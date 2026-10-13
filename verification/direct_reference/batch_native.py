"""Disposable PostgreSQL acceptance and actual batch DB accounting."""
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.orm import Session
from app.db.models import Base,Application,ApplicationLifecycleEvent
from . import batch as b,batch_transaction as t,batch_supervisor as supervisor
from .fixtures import Session as Source,summary
from tests.test_stage4_batch import seed,source,LIMITS,SHA

@pytest.fixture()
def engine():
    assert os.environ.get('B20_DISPOSABLE')=='YES_SYNTHETIC_ONLY' and not os.environ.get('DATABASE_URL')
    port=int(os.environ['B20_POSTGRES_PORT']);assert 1024<=port<=65535
    e=create_engine(f'postgresql+psycopg://b20_disposable:b20-disposable-only@127.0.0.1:{port}/b20_disposable',pool_size=1,max_overflow=0,connect_args={'connect_timeout':5,'options':'-c statement_timeout=10000 -c lock_timeout=8000 -c idle_in_transaction_session_timeout=40000'})
    with e.connect() as c:assert c.execute(text('SHOW server_version')).scalar_one().startswith('17.')
    Base.metadata.drop_all(e);Base.metadata.create_all(e);seed(e)
    yield e
    assert e.pool.checkedout()==0;e.dispose()

@pytest.fixture(autouse=True)
def no_council():
    with patch('requests.sessions.Session.request',side_effect=AssertionError('Council forbidden')):yield

def test_supervised20(engine,tmp_path):
    import subprocess
    candidate=os.environ['BATCH_REPOSITORY_SHA']
    assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==candidate
    rows=b.manifest();indices={r['identity']['application_id']:n for n,r in enumerate(rows)}
    def worker(r,l):
        def command(row,limits,out):return [sys.executable,'-m','verification.direct_reference.batch_supervisor','--index',str(indices[row['application_id']]),'--limits',json.dumps(limits),'--output',str(out)]
        return supervisor.isolated(r,l,command,dict(B20_DISPOSABLE='YES_SYNTHETIC_ONLY',B20_POSTGRES_PORT=os.environ['B20_POSTGRES_PORT']))
    result=b.run(candidate,'disposable-supervised20',worker)
    assert result['assessment']=='ACCOUNTED',result
    assert all(r['transaction']=='COMMITTED' and r['cleanup']=='CLOSED' for r in result['records'])
    counts={k:sum(r['statements'][k] for r in result['records']) for k in ('reads','writes','other','commits','rollbacks','connections')}
    assert counts['commits']==20
    assert all(r['statements']['peak_connections']==1 for r in result['records'])
    result['totals'] # validated by the parent
    destination=os.environ.get('BATCH_EVIDENCE_DIR')
    if destination:
        p=Path(destination);p.mkdir(parents=True,exist_ok=True)
        (p/'batch-audit.json').write_bytes(b.encode(result))
        (p/'statement-accounting.json').write_text(json.dumps(dict(total=sum(counts[k] for k in ('reads','writes','other')),totals=counts,per_record=[dict(application_id=r['application_id'],**r['statements']) for r in result['records']]),indent=2))
    print('BATCH_ACTUAL_DB_ACCOUNTING',json.dumps(counts,sort_keys=True))
    replay=b.run(SHA,'idempotent',lambda r,l:t.run_transaction(engine,r,lambda:source(r),l))
    assert all(r['b2_outcome']=='VERIFIED_UNCHANGED' for r in replay['records'])
    assert all(len(r['after']['events'])==1 for r in replay['records'])

@pytest.mark.parametrize('case',['rollback12','lost_ack','uncertain_readback','stale','withheld'])
def test_transaction_failures(engine,monkeypatch,case):
    rows=b.manifest();target=rows[11]['identity']['application_id'] if case=='rollback12' else rows[0]['identity']['application_id']
    original_commit=Session.commit;original_snapshot=t.snapshot
    def commit(s):
        app=next((x for x in s.identity_map.values() if isinstance(x,Application)),None)
        if app and app.id==target:
            if case=='rollback12':raise RuntimeError('Synthetic rollback')
            if case=='lost_ack':original_commit(s);raise RuntimeError('Synthetic lost ack')
        return original_commit(s)
    if case in {'rollback12','lost_ack'}:monkeypatch.setattr(Session,'commit',commit)
    counter=[]
    def snapshot(s,r):
        if r['application_id']==target:
            counter.append(1)
            if case=='uncertain_readback' and len(counter)==3:raise RuntimeError('Synthetic reader unavailable')
        return original_snapshot(s,r)
    if case=='uncertain_readback':monkeypatch.setattr(t,'snapshot',snapshot)
    def execute(r,l):
        if case=='withheld' and r['application_id']==target:
            with Session(engine) as s:
                a=s.get(Application,target);a.status='Decided';a.decision='Granted';a.decision_issued_date='2026-10-01';s.commit()
            return t.run_transaction(engine,r,lambda:Source(summary(r['reference'],status='Decided',decision='Refuse Permission',date='Fri 25 Sep 2026')),l)
        if case=='stale' and r['application_id']==target:
            other=create_engine(engine.url,pool_size=1,max_overflow=0)
            def newer():
                try:
                    accepted=t.run_transaction(other,r,lambda:source(r),l)
                    assert accepted['transaction']=='COMMITTED'
                    return source(r)
                finally:other.dispose()
            return t.run_transaction(engine,r,newer,l)
        return t.run_transaction(engine,r,lambda:source(r),l)
    out=b.run(SHA,case,execute)
    if case=='rollback12':
        assert all(r['transaction']=='COMMITTED' for r in out['records'][:11])
        assert out['records'][11]['transaction']=='NOT_COMMITTED' and out['records'][11]['disposition']=='SAFETY_STOP'
        assert all(r['disposition']=='NOT_ATTEMPTED' for r in out['records'][12:])
    elif case=='lost_ack':
        assert out['records'][0]['transaction']=='COMMITTED' and out['records'][0]['b2_outcome']=='PERSISTENCE_FAILED'
        assert out['assessment']=='ACCOUNTED'
    elif case=='uncertain_readback':
        assert out['records'][0]['transaction']=='UNKNOWN'
        with pytest.raises(ValueError):b.run(SHA,'blocked-resume',execute,prior=out,prior_sha256=hashlib.sha256(b.encode(out)).hexdigest())
    elif case=='withheld':
        assert out['records'][0]['disposition']=='SAFELY_REJECTED' and out['records'][1]['transaction']=='COMMITTED'
    else:
        assert out['records'][0]['b2_outcome']=='STALE_RESPONSE'
        assert out['records'][0]['transaction']=='UNKNOWN' and out['assessment']=='STOPPED_REVIEW_REQUIRED'

def test_native_partial_resume(engine):
    calls=[]
    def clock():return 0 if len(calls)<11 else 300
    def execute(r,l):calls.append(r['application_id']);return t.run_transaction(engine,r,lambda:source(r),l)
    partial=b.run(SHA,'partial',execute,clock=clock)
    assert len(calls)==11
    done=b.run(SHA,'resume',execute,prior=partial,prior_sha256=hashlib.sha256(b.encode(partial)).hexdigest())
    assert len(calls)==20 and len(set(calls))==20 and done['assessment']=='ACCOUNTED'
    assert all(len(r['after']['events'])==1 for r in done['records'])

@pytest.mark.parametrize('case',['commit','dispose_failure'])
def test_production_wrapper_disposable_only(engine,monkeypatch,tmp_path,case):
    from . import batch_production as live,oldham_production,refresh
    row=b.manifest()[0]['identity']
    monkeypatch.setattr(live,'resource_limits',lambda:None) # supervisor limit proof is test_supervised20
    calls=[]
    def production_engine(**kwargs):
        calls.append(kwargs);return engine
    monkeypatch.setattr(oldham_production,'production_engine',production_engine)
    monkeypatch.setattr(refresh,'requests_session',lambda:source(row))
    if case=='dispose_failure':monkeypatch.setattr(engine,'dispose',lambda:(_ for _ in ()).throw(RuntimeError('Synthetic cleanup failure')))
    output=tmp_path/'production-wrapper-synthetic.json'
    assert live.worker(row,LIMITS,output)==0
    result=json.loads(output.read_text());b.validate_record(result,row)
    assert result['transaction']=='COMMITTED' and result['source_provenance']=='FRESH_OFFICIAL_SUMMARY'
    # This test-only factory patch is explicitly synthetic. It is not a production
    # observation and its individual audit is not exported as live evidence.
    assert calls==[dict(secret_name='BATCH_DATABASE_URL',application_name='stage4_representative20_once')]
    if case=='commit':assert result['cleanup']=='CLOSED' and result['disposition']=='COMPLETED'
    else:assert result['cleanup']=='FAILED' and result['disposition']=='SAFETY_STOP'
