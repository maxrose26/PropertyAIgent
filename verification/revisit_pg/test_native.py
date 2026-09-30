"""Native PostgreSQL only. Missing isolated runner is BLOCKED, never skipped."""
import datetime as dt
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, text, update, func
from sqlalchemy.exc import DBAPIError
from app.db.models import Base, Council, ScrapeRun
from app.pipeline.discovery_owner import DiscoveryOwner
from app.revisit.schema import work, attempts, versions, observations, relationships, TABLE_NAMES
from app.revisit.migration import migrate, verify
from app.revisit.storage import Store
from app.revisit.stage import run_recorded_stage

@pytest.fixture
def engine():
    if 'AH_DISPOSABLE_ROOT' not in os.environ:
        pytest.fail('BLOCKED: run only through namespace-isolated revisit PostgreSQL runner')
    from verification.ah_pg.cluster import provision_case,destroy_case
    engine,manifest=provision_case(os.environ['AH_DISPOSABLE_ROOT'])
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:destroy_case(engine,manifest)

@pytest.fixture
def admitted(engine,tmp_path,monkeypatch):
    with engine.begin() as c:
        migrate(c)
        c.execute(Council.__table__.insert().values(code='stockport',name='Fixture',base_url='https://example.invalid',date_field_mode='received',doc_system='idox'))
    with DiscoveryOwner(str(tmp_path/'owner.lock')) as owner:
        with engine.begin() as c:
            run=c.execute(ScrapeRun.__table__.insert().values(council_code='stockport',status='running',
                started_at=dt.datetime.now(dt.timezone.utc),progress=json.dumps({'owner':owner.identity,'limits':{'effective_council_seconds':120}})).returning(ScrapeRun.id)).scalar_one()
        for key,value in owner.child_environment(run).items():
            if key.startswith('PROPERTYAIGENT_OWNER') or key=='PROPERTYAIGENT_RUN_ID':monkeypatch.setenv(key,value)
        yield engine,Store(engine,'stockport'),owner,run


def response(ticket,body=b'72 proposed retirement apartments'):
    return dict(cursor=ticket['cursor'],next=None,documents=[dict(council='stockport',reference=ticket['reference'],
        url='https://example.invalid/statement.pdf',body=body,stage='submitted_statement',issued='2024-10-23',published='2024-10-24')])


def document_ticket(store,ref='DC/093884'):
    store.seed(ref)
    ticket=store.reserve()
    assert ticket['stage']=='documents'
    return ticket


def count(engine,table):
    with engine.connect() as c:return c.execute(select(func.count()).select_from(table)).scalar_one()


def test_migration_repeatable_and_p0a_unchanged(engine):
    from scripts.migrate_p0a import verify_definitions
    with engine.begin() as c:
        assert verify(c,allow_missing=True)['revisit_missing']
        migrate(c);migrate(c)
        assert not verify(c)['revisit_missing']
        assert verify_definitions(c,allow_missing=False)==[]


def test_before_p0a_state_verifies_but_revisit_apply_rejected(engine):
    with engine.begin() as c:
        c.execute(text('DROP TABLE parent_lookup_work'))
        c.execute(text('ALTER TABLE scrape_runs DROP COLUMN progress'))
        assert set(verify(c,allow_missing=True)['p0a_missing'])=={'parent_lookup_work','scrape_runs.progress'}
        with pytest.raises(RuntimeError,match='P0-A'):migrate(c)


def test_unrelated_table_and_partial_schema_rejected(engine):
    with engine.begin() as c:
        c.execute(text('CREATE TABLE unrelated_drift (id integer)'))
        with pytest.raises(RuntimeError,match='unrelated'):verify(c,True)
        c.execute(text('DROP TABLE unrelated_drift'))
        work.create(c)
        with pytest.raises(RuntimeError,match='partial'):verify(c,True)


def test_migration_rollback(engine):
    with engine.connect() as c:
        tx=c.begin();migrate(c);tx.rollback()
        assert verify(c,True)['revisit_missing']


def test_atomic_rollback_keeps_evidence_and_cursor_uncommitted(admitted):
    engine,store,_,_=admitted
    ticket=document_ticket(store)
    invalid=response(ticket)
    invalid['documents'].append(dict(invalid['documents'][0],reference='DC/095922'))
    with pytest.raises(ValueError,match='scope'):store.finish(ticket,invalid)
    assert count(engine,versions)==count(engine,observations)==0
    with engine.connect() as c:
        assert c.execute(select(work.c.cursor).where(work.c.id==ticket['id'])).scalar_one()=='start'
    assert store.finish(ticket,response(ticket))=='complete'


def test_duplicate_response_and_new_check_unchanged_bytes(admitted):
    engine,store,_,_=admitted
    ticket=document_ticket(store)
    result=response(ticket)
    store.finish(ticket,result)
    assert store.finish(ticket,result)=='duplicate'
    assert count(engine,observations)==1
    # Explicit local recheck selection fixture; no live cadence/activation.
    with engine.begin() as c:
        c.execute(update(work).where(work.c.id==ticket['id']).values(outcome='pending',cursor='start',due=0,last_attempt=None))
    ticket=store.reserve();store.finish(ticket,response(ticket))
    assert count(engine,versions)==1 and count(engine,observations)==2


def test_same_url_changed_body_keeps_original(admitted):
    engine,store,_,_=admitted
    ticket=document_ticket(store);store.finish(ticket,response(ticket,b'original'))
    with engine.begin() as c:c.execute(update(work).where(work.c.id==ticket['id']).values(outcome='pending',cursor='start',due=0,last_attempt=None))
    ticket=store.reserve();store.finish(ticket,response(ticket,b'revised'))
    with engine.connect() as c:assert c.execute(select(versions.c.body).order_by(versions.c.id)).scalars().all()==[b'original',b'revised']


@pytest.mark.parametrize('table',[versions,observations,relationships])
def test_evidence_mutation_protection_and_connection_recovery(admitted,table):
    engine,store,_,_=admitted
    ticket=document_ticket(store);store.finish(ticket,response(ticket))
    with engine.connect() as c:
        with pytest.raises(DBAPIError,match='immutable'):c.execute(table.delete())
        c.rollback()
        assert c.execute(text('SELECT 1')).scalar_one()==1


def test_concurrent_reservation_distinct_and_stale_completion_rejected(admitted):
    engine,store,_,_=admitted
    store.seed('DC/093884')
    with ThreadPoolExecutor(max_workers=2) as pool:
        tickets=list(pool.map(lambda _:store.reserve(),range(2)))
    assert len({t['id'] for t in tickets})==2
    t=tickets[0]
    with engine.begin() as c:c.execute(update(work).where(work.c.id==t['id']).values(generation=t['generation']+1))
    with pytest.raises(RuntimeError,match='stale'):store.finish(t,response(t))


def test_run_id_without_matching_owner_rejected(admitted):
    engine,store,_,run=admitted
    with engine.begin() as c:c.execute(update(ScrapeRun).where(ScrapeRun.id==run).values(progress=json.dumps({'owner':{'invocation':'wrong'}})))
    with pytest.raises(RuntimeError,match='owner mismatch'):store.reserve()


def test_unresolved_owner_cannot_be_recovered(admitted):
    engine,store,owner,run=admitted
    t=document_ticket(store)
    with engine.begin() as c:
        old=c.execute(ScrapeRun.__table__.insert().values(council_code='stockport',status='failed',progress=json.dumps({'owner':owner.identity})).returning(ScrapeRun.id)).scalar_one()
        c.execute(update(work).where(work.c.id==t['id']).values(owner_run=old))
    with pytest.raises(RuntimeError,match='terminal'):store.recover()


def test_exited_process_successor_recovery_invalidates_old_ticket(admitted):
    engine,store,owner,run=admitted
    # Real exited process identity, not a monkeypatch of terminal_evidence.
    code='import json,os;from app.pipeline.discovery_owner import process_identity;print(json.dumps([os.getpid(),process_identity(os.getpid())]))'
    pid,start=json.loads(subprocess.check_output([sys.executable,'-c',code]))
    old_identity=dict(owner.identity,pid=pid,pid_start=start,invocation='prior-fixture-invocation')
    t=document_ticket(store)
    with engine.begin() as c:
        old=c.execute(ScrapeRun.__table__.insert().values(council_code='stockport',status='failed',progress=json.dumps({'owner':old_identity})).returning(ScrapeRun.id)).scalar_one()
        c.execute(update(work).where(work.c.id==t['id']).values(owner_run=old,owner_invocation=old_identity['invocation']))
    assert store.recover()==1
    with pytest.raises(RuntimeError,match='stale'):store.finish(t,response(t))
    assert count(engine,observations)==0


def test_relationship_and_frontier_atomic_scope(admitted):
    engine,store,_,_=admitted
    t=document_ticket(store);store.finish(t,response(t))
    t=store.reserve()
    edges=[dict(council='stockport',reference='DC/094889',type='discharge',confidence='verified_reference',citation='DC/093884'),
           dict(council='tameside',reference='SITE/313',type='variation',confidence='verified_reference',citation='same address')]
    store.finish(t,dict(cursor=t['cursor'],next=None,edges=edges))
    assert count(engine,relationships)==2 and count(engine,work)==4
    with engine.connect() as c:assert c.execute(select(work.c.council).distinct()).scalars().all()==['stockport']


def test_finite_stage_limit_reports_deferred_work(admitted):
    engine,store,_,_=admitted
    for ref in ['A','B','C']:store.seed(ref)
    records={}
    for ref in ['a','b','c']:
        records['stockport/'+ref+'/register']=dict(status=200,chunks=[b'<table></table>'])
        records['stockport/'+ref+'/relationships/start']=dict(status=200,chunks=[b'{"next":null,"edges":[]}'])
    result=run_recorded_stage(engine,'stockport',records)
    assert result['completed_responses']==2 and result['pending']==4
    assert result['outcome']=='partial'


def test_ordinary_engine_denied_before_connect():
    from sqlalchemy import create_engine
    from app.revisit.migration import apply_local
    engine=create_engine('postgresql+psycopg://invalid:invalid@127.0.0.1:1/invalid')
    try:
        with pytest.raises(ValueError,match='migration remains disabled'):apply_local(engine)
    finally:engine.dispose()


@pytest.mark.parametrize('replacement', [
    "CHECK (stage IN ('documents','relationships','anything'))",
    "CHECK (stage IN ('documents','relationships')) NOT VALID",
    "CHECK (stage IN ('documents','relationships')) NO INHERIT",
])
def test_real_stage_constraint_drift_rejected(engine,replacement):
    with engine.begin() as c:
        migrate(c)
        c.execute(text('ALTER TABLE revisit_work DROP CONSTRAINT ck_revisit_stage'))
        c.execute(text('ALTER TABLE revisit_work ADD CONSTRAINT ck_revisit_stage '+replacement))
        with pytest.raises(RuntimeError,match='stage check drift'):verify(c)
