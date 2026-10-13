import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest
import requests
from sqlalchemy.orm import Session
from app.db.models import Application,Council
from verification.direct_reference import batch as b
from verification.direct_reference import batch_transaction as t
from verification.direct_reference.fixtures import Session as Source,summary

SHA='a'*40
LIMITS=dict(requests=2,bytes=2_000_000,seconds=40,worker_seconds=45)

def seed(engine):
    with Session(engine) as s:
        for entry in b.manifest():
            r=entry['identity']
            if not s.get(Council,r['council']):s.add(Council(code=r['council'],name=r['council'],base_url=r['source_url'].split('/applicationDetails.do')[0],date_field_mode='received',doc_system='idox'))
            s.add(Application(id=r['application_id'],council_code=r['council'],reference=r['reference'],status='Awaiting decision'))
        s.commit()

def source(row):return Source(summary(row['reference'],status='Decided',decision='Granted',date='Fri 25 Sep 2026'))

def execute(engine,row,limits):return t.run_transaction(engine,row,lambda:source(row),limits)

def test_manifest_exact():
    rows=b.manifest()
    assert [r['identity']['application_id'] for r in rows]==[72,468,197,18,381,41,409,37,126,187,45,53,54,56,305,783,289,220,209,499]
    from collections import Counter
    assert Counter(r['policy'] for r in rows)==dict(A=8,E=8,F=4)
    assert len({r['identity']['council'] for r in rows})==7
    assert hashlib.sha256(Path(b.__file__).with_name('batch-manifest.json').read_bytes()).hexdigest()==b.MANIFEST_SHA256

def test_all20(session):
    e=session.get_bind();seed(e)
    out=b.run(SHA,'offline20',lambda row,limits:execute(e,row,limits))
    assert out['assessment']=='ACCOUNTED',out
    assert all(r['transaction']=='COMMITTED' for r in out['records'])
    assert out['totals']['requests']==20
    assert all(len(r['after']['events'])==1 for r in out['records'])
    replay=b.run(SHA,'replay',lambda row,limits:execute(e,row,limits))
    assert all(r['b2_outcome']=='VERIFIED_UNCHANGED' for r in replay['records'])
    assert all(len(r['after']['events'])==1 for r in replay['records'])

@pytest.mark.parametrize('case',['missing','unknown','timeout','rate','parser'])
def test_local_continue(session,case):
    e=session.get_bind();seed(e);first=b.manifest()[0]['identity']['application_id']
    def fn(r,l):
        factory=lambda:source(r)
        if r['application_id']==first:
            body=summary(r['reference'],status='Deposited',omit=('Decision','Decision Issued Date')) if case=='missing' else summary(r['reference'],status='Registered') if case=='unknown' else requests.Timeout() if case=='timeout' else b'<html>incompatible</html>' if case=='parser' else summary(r['reference'])
            factory=lambda:Source(body,status=429 if case=='rate' else 200)
        return t.run_transaction(e,r,factory,l)
    out=b.run(SHA,case,fn)
    assert out['records'][0]['disposition']=='SAFELY_REJECTED',out['records'][0]
    assert out['records'][1]['disposition']=='COMPLETED'
    assert out['records'][0]['before']==out['records'][0]['after']

@pytest.mark.parametrize('case',['wrong','redirect','overflow'])
def test_safety_stop(session,case):
    e=session.get_bind();seed(e)
    def fn(r,l):
        body=summary('WRONG') if case=='wrong' else b'x'*1_000_001 if case=='overflow' else summary(r['reference'])
        return t.run_transaction(e,r,lambda:Source(body,status=302 if case=='redirect' else 200),l)
    out=b.run(SHA,case,fn)
    assert out['assessment']=='STOPPED_REVIEW_REQUIRED'
    assert out['records'][0]['disposition'] in {'SAFETY_STOP','UNCERTAIN'}
    assert all(r['disposition']=='NOT_ATTEMPTED' for r in out['records'][1:])

def test_partial_resume(session):
    e=session.get_bind();seed(e);calls=[]
    def clock():return 0 if len(calls)<11 else 300
    def fn(r,l):calls.append(r['application_id']);return execute(e,r,l)
    out=b.run(SHA,'partial',fn,clock=clock)
    assert len(calls)==11 and out['assessment']=='STOPPED_REVIEW_REQUIRED'
    later=[]
    def rest(r,l):later.append(r['application_id']);return execute(e,r,l)
    done=b.run(SHA,'resume',rest,prior=out,prior_sha256=hashlib.sha256(b.encode(out)).hexdigest())
    assert len(later)==9 and done['assessment']=='ACCOUNTED' and len(done['carried_ids'])==11
    assert not set(later)&set(calls)

def test_resume_uncertain_and_corrupt(session):
    e=session.get_bind();seed(e)
    out=b.run(SHA,'bad',lambda r,l:(_ for _ in ()).throw(RuntimeError('private error')))
    assert 'private error' not in b.encode(out).decode()
    with pytest.raises(ValueError):b.run(SHA,'next',lambda *a:None,prior=out,prior_sha256=hashlib.sha256(b.encode(out)).hexdigest())
    bad=copy.deepcopy(out);bad['records'][0]['password']='forbidden'
    with pytest.raises(ValueError):b.validate(bad)

def test_normalization(session):
    e=session.get_bind();seed(e);r=b.manifest()[0]['identity']
    with Session(e) as s:
        app=s.get(Application,r['application_id']);app.status='Decided';app.decision='Granted';app.decision_issued_date='Fri 25 Sep 2026';s.commit()
    out=execute(e,r,LIMITS)
    assert out['b2_outcome']=='VERIFIED_NON_MATERIAL_CHANGE' and out['after']['events']==[]

def test_sql_denied(session):
    from sqlalchemy import text,update,event
    e=session.get_bind();seed(e);r=b.manifest()[0]['identity'];g=t.install_guards(e,r)
    try:
        for q in (text('SELECT 1'),update(Application).where(Application.id==r['application_id']).values(status='BAD')):
            with pytest.raises(ValueError):
                with e.begin() as c:c.execute(q)
    finally:event.remove(e,'before_execute',g)

def test_optional_blank(session):
    e=session.get_bind();seed(e);r=b.manifest()[0]['identity']
    out=t.run_transaction(e,r,lambda:Source(summary(r['reference'])),LIMITS)
    assert out['transaction']=='COMMITTED' and out['b2_outcome']=='VERIFIED_UNCHANGED'
    assert out['source']['field_states']['decision']=='PRESENT_BLANK'

@pytest.mark.parametrize('case',['privacy','cleanup'])
def test_privacy_cleanup_stop(session,case):
    e=session.get_bind();seed(e)
    class Broken(Source):
        def close(self):raise RuntimeError('Private diagnostic must not escape')
    def fn(r,l):
        factory=lambda:Broken(summary(r['reference'])) if case=='cleanup' else Source(summary(r['reference'],status='private@example.com'))
        return t.run_transaction(e,r,factory,l)
    out=b.run(SHA,case,fn)
    assert out['assessment']=='STOPPED_REVIEW_REQUIRED'
    assert all(r['disposition']=='NOT_ATTEMPTED' for r in out['records'][1:])
    assert 'private@example.com' not in b.encode(out).decode()
    assert 'Private diagnostic' not in b.encode(out).decode()

def test_worker_no_audit_is_unknown(monkeypatch,tmp_path):
    from verification.direct_reference import batch_supervisor as sup
    monkeypatch.setattr(sup,'supervise',lambda *a,**k:(-9,True))
    row=b.manifest()[0]['identity']
    out=sup.isolated(row,LIMITS,lambda *a:['never-executed'],{})
    assert out['transaction']=='UNKNOWN' and out['cleanup']=='UNKNOWN'
    result=b.run(SHA,'timeout',lambda *a:out)
    assert set(result['totals'].values())=={'UNKNOWN'}

def test_bad_resume_digest(session):
    e=session.get_bind();seed(e)
    out=b.run(SHA,'first',lambda r,l:execute(e,r,l))
    with pytest.raises(ValueError):b.run(SHA,'second',lambda *a:None,prior=out,prior_sha256='0'*64)

def test_frozen_manifest_digest(monkeypatch):
    original=Path.read_bytes
    def corrupt(p):return b'{}' if p.name=='batch-manifest.json' else original(p)
    monkeypatch.setattr(Path,'read_bytes',corrupt)
    with pytest.raises(ValueError):b.manifest()
