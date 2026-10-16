"""Disposable-only worker interface. No source clients or production permissions."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import create_engine, select, func
from app.ingestion.schema import install, WorkItem as W, WorkAttempt as A
from app.ingestion.ledger import Ledger, Denied, StaleClaim, digest
from app.ingestion.worker_interface import WorkerInterface, TaskBinding


def binding(l, key):
 r=l.get(key)
 return TaskBinding(key,r['task'],r['contract'],r['revision'],digest(r['subject']))


def task(l, reference='FIXTURE/26', **kw):
 return l.enqueue({'kind':'APPLICATION','council':'manchester','reference':reference},'SCREENING',contract='retained-fixture-v1',**kw)


def validator(row, evidence):
 return evidence=={'reference':row['subject']['reference'],'retained_sha256':'a'*64}


def worker(l, keys, owner='worker'):
 return WorkerInterface(l,owner=owner,authority='INGESTION_TEST_worker',bindings=[binding(l,k) for k in keys],validators={'retained-fixture-v1':validator})


def grant(l,keys):
 l.grant('INGESTION_TEST_worker',keys,expires_at=5000,contracts=['retained-fixture-v1'])


@pytest.fixture
def fixture():
 e=create_engine('sqlite:///:memory:');install(e);clock=[1000.0];l=Ledger(e,clock=lambda:clock[0])
 yield l,clock
 e.dispose()


def test_binding_does_not_grant_execution_and_no_administrative_surface(fixture):
 l,_=fixture;k=task(l);w=worker(l,[k])
 for name in ('grant','enqueue','recover','engine','intent','fenced_effect','finish','stop','release'):
  assert not hasattr(w,name)
 with pytest.raises(Denied,match='AUTHORITY'):w.claim(k)
 with pytest.raises(Denied,match='NO_LIVE'):WorkerInterface(l,owner='worker',authority='AUTHORISE_STORAGE_TLS_CATALOGUE_ONCE_20261016',bindings=[binding(l,k)],validators={'retained-fixture-v1':validator})


def test_scoped_checkpoint_is_durable_in_both_item_and_attempt(fixture):
 l,_=fixture;k=task(l);other=task(l,'OTHER');grant(l,[k,other]);w=worker(l,[k]);c=w.claim(k)
 with pytest.raises(Denied,match='NOT_BOUND'):w.claim(other)
 evidence={'reference':'FIXTURE/26','retained_sha256':'a'*64};assert w.checkpoint(c,evidence)==digest(evidence)
 assert l.get(k)['checkpoint']==evidence and l.get(k)['state']=='CLAIMED'
 with l.engine.connect() as db:assert db.execute(select(A.c.checkpoint)).scalar_one()==evidence
 with pytest.raises(Denied,match='CHECKPOINT_CONTRACT'):w.checkpoint(c,{'verified_facts':True})
 assert l.get(k)['checkpoint']==evidence


def test_stale_worker_cannot_checkpoint_after_claim_recovery(fixture):
 l,clock=fixture;k=task(l);grant(l,[k]);w=worker(l,[k]);c=w.claim(k,lease_seconds=1);clock[0]+=2
 l.recover(c,cleanup_closed=True)
 with pytest.raises((Denied,StaleClaim)):w.checkpoint(c,{'reference':'FIXTURE/26','retained_sha256':'a'*64})
 fresh=worker(l,[k],owner='replacement');n=fresh.claim(k)
 assert n.fence>c.fence
 with pytest.raises(Denied):fresh.checkpoint(c,{})
 assert l.get(k)['checkpoint'] is None


@pytest.mark.parametrize('state',['SAFETY_BLOCKED','UNSUPPORTED_CONTRACT','PERSISTENCE_UNCERTAIN'])
def test_blocked_tasks_remain_blocked(fixture,state):
 l,_=fixture;k=task(l,state=state,reason='REVIEW');grant(l,[k]);w=worker(l,[k])
 with pytest.raises(Denied):w.claim(k)
 assert l.get(k)['attempt_count']==0


def test_dependency_global_stop_and_uncertain_write_barrier_are_preserved(fixture):
 l,_=fixture;parent=task(l,'PARENT');child=task(l,dependencies=[parent]);grant(l,[parent,child]);w=worker(l,[child])
 with pytest.raises(Denied,match='DEPENDENCY'):w.claim(child)
 c=l.claim(parent,'controller','INGESTION_TEST_worker');l.finish(c,{'outcome':'FIXTURE_ONLY'})
 l.stop('CONSUMED_SALFORD_STOP')
 with pytest.raises(Denied,match='GLOBAL_STOP'):w.claim(child)
 assert l.get(child)['attempt_count']==0


def test_effect_intents_and_changed_binding_not_resolved_by_worker(fixture):
 l,_=fixture;k=task(l);grant(l,[k]);w=worker(l,[k]);c=w.claim(k)
 with l.engine.begin() as db:db.execute(W.update().where(W.c.key==k).values(phase='WRITE_INTENT'))
 with pytest.raises(Denied,match='EFFECT_RESOLUTION'):w.checkpoint(c,{})
 with l.engine.begin() as db:db.execute(W.update().where(W.c.key==k).values(revision='tampered'))
 with pytest.raises(Denied,match='BINDING_CHANGED'):w.checkpoint(c,{})


def test_uncertain_write_barrier_blocks_an_independent_claim(fixture):
 l,_=fixture;uncertain=task(l,'UNCERTAIN');other=task(l,'OTHER');grant(l,[uncertain,other])
 c=l.claim(uncertain,'controller','INGESTION_TEST_worker')
 with l.engine.begin() as db:db.execute(W.update().where(W.c.key==uncertain).values(phase='WRITE_INTENT'))
 with pytest.raises(Denied,match='WRITE_BARRIER'):worker(l,[other]).claim(other)
 assert l.get(other)['attempt_count']==0


def test_duplicate_concurrent_delivery_creates_one_attempt():
 import tempfile,os
 fd,path=tempfile.mkstemp(prefix='ingestion-test-',dir='/tmp');os.close(fd)
 e=create_engine('sqlite:///'+path);install(e);l=Ledger(e,clock=lambda:1000.0)
 try:
  k=task(l);grant(l,[k]);barrier=Barrier(2)
  def run(owner):
   w=worker(l,[k],owner);barrier.wait()
   try:return w.claim(k)
   except Denied:return None
  with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(run,['one','two']))
  assert sum(c is not None for c in claims)==1
  with e.connect() as db:assert db.scalar(select(func.count()).select_from(A))==1
 finally:e.dispose();os.unlink(path)
