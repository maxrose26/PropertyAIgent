"""No live DNS or database: actual frozen class and captured driver arguments."""
import json,os,subprocess
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
import pytest
from verification.ingestion_storage import tameside_owner_database as m

@pytest.mark.parametrize('answers',[[m.ADDRESS,'18.135.253.94'],['18.135.253.94',m.ADDRESS],['18.135.253.94','18.169.213.251',m.ADDRESS],[m.ADDRESS]])
def test_order_and_additional_answers(monkeypatch,answers):
    calls=[]
    def run(args,**kw):
        calls.append((args,kw));return SimpleNamespace(returncode=0,stdout=json.dumps(answers).encode())
    monkeypatch.setattr(m.subprocess,'run',run)
    assert m.approved_address(m.HOST,m.PORT)==m.ADDRESS
    assert len(calls)==1
    args,kw=calls[0]
    assert args[1:3]==['-I','-c'] and args[3]==m.DNS_CODE
    assert kw['timeout']==3 and kw['env']=={'LANG':'C.UTF-8'}
    assert kw['stderr']==subprocess.DEVNULL and kw['stdin']==subprocess.DEVNULL

@pytest.mark.parametrize('raw,code',[(b'["18.135.253.94"]','TAMESIDE_APPROVED_ADDRESS_ABSENT'),(b'[]','TAMESIDE_DNS_REFUSED'),(b'x'*4097,'TAMESIDE_DNS_REFUSED'),(b'["not-ip"]','TAMESIDE_DNS_REFUSED'),(b'null','TAMESIDE_DNS_REFUSED')])
def test_refused_answers(monkeypatch,raw,code):
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=raw))
    with pytest.raises(ValueError,match=code):m.approved_address(m.HOST,m.PORT)

@pytest.mark.parametrize('error',[subprocess.TimeoutExpired('dns',3),OSError('dns')])
def test_dns_failure_no_retry(monkeypatch,error):
    calls=[]
    def run(*a,**k):calls.append(1);raise error
    monkeypatch.setattr(m.subprocess,'run',run)
    with pytest.raises(ValueError,match='TAMESIDE_DNS_REFUSED'):m.approved_address(m.HOST,m.PORT)
    assert len(calls)==1

def root():
    p=os.environ.get('S4_BOLTON_PINNED_CHECKOUT')
    if not p:pytest.skip('pinned #213 checkout required')
    return p

@pytest.mark.parametrize('fails',[False,True])
def test_actual_frozen_connection_tls_and_no_fallback(monkeypatch,fails):
    import psycopg
    from verification.ingestion_storage import tls_trust
    original_run=m.subprocess.run
    dns=[];attempts=[]
    def run(*a,**k):dns.append(1);return SimpleNamespace(returncode=0,stdout=json.dumps(['18.135.253.94',m.ADDRESS]).encode())
    monkeypatch.setattr(m.subprocess,'run',run)
    monkeypatch.setattr(tls_trust,'verified_trust',lambda:('/fixture/verified-ca.pem','fixture'))
    @contextmanager
    def connect(**kw):
        attempts.append(kw)
        if fails:raise OSError('connection failed')
        c=SimpleNamespace(closed=False)
        try:yield c
        finally:c.closed=True
    monkeypatch.setattr(psycopg,'connect',connect)
    db=m.database_type(root())({'DATABASE_URL':'postgresql://postgres.zcikcfgpblzuzpanpdqd:fixture@'+m.HOST+':5432/postgres'})
    if fails:
        with pytest.raises(OSError,match='connection failed'):
            with db.connection():pass
    else:
        with db.connection() as c:assert not c.closed
        assert c.closed
    assert len(dns)==len(attempts)==1
    kw=attempts[0]
    assert kw['host']==m.HOST and kw['hostaddr']==db.address==m.ADDRESS and kw['port']==5432
    assert kw['sslmode']=='verify-full' and kw['sslrootcert']=='/fixture/verified-ca.pem'
    assert kw['connect_timeout']==5 and kw['autocommit'] is True
    assert kw['options']=='-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000'
    monkeypatch.setattr(m.subprocess,'run',original_run)
    from verification.ingestion_storage.tameside_package import seal_policy
    from verification.ingestion_storage.tameside_candidate import validate_job
    policy=seal_policy(manifest_sha256='a'*64,bound_at=1794942000,hostaddr=db.address)
    assert policy['hostaddr']==db.address
    env=dict(RENDER_SERVICE_ID='crn-d9sv93vavr4c73f98rb0',RENDER_GIT_COMMIT=policy['execution_binding']['revision'],INGESTION_WORKER_DATABASE_URL='fixture',INGESTION_EFFECT_DATABASE_URL='fixture')
    assert validate_job(policy,hostaddr=db.address,access_deadline=1794944100,now=1794942001,environ=env)
    with pytest.raises(ValueError,match='TARGET_OR_DEADLINE'):
        validate_job(policy,hostaddr='18.135.253.94',access_deadline=1794944100,now=1794942001,environ=env)

def test_frozen_source_drift_refuses(tmp_path):
    p=tmp_path/'verification/ingestion_storage';p.mkdir(parents=True)
    (p/'owner_pilot.py').write_text('class Database: pass')
    with pytest.raises(ValueError,match='SOURCE_DRIFT'):m.database_type(tmp_path)

def test_route_drift_before_dns(monkeypatch):
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**k:pytest.fail('must not resolve'))
    with pytest.raises(ValueError,match='ROUTE_DRIFT'):m.approved_address(m.HOST,6543)
