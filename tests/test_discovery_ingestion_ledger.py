"""Shared coordinator offline SQLite acceptance; never uses application get_engine."""
import json,time
from pathlib import Path
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import create_engine,select,func,inspect
from app.ingestion.schema import install,uninstall_empty,WorkItem as W,WorkAttempt as A,metadata
from app.ingestion.ledger import Ledger,Denied,StaleClaim,UncertainPersistence,digest,DEFAULT_LIMITS
from app.ingestion.coordinator import Coordinator,ListingContract
from verification.discovery.arcus_ui_config import SCREENING_CONFIG,SCREENING_CASE,dated_config
from tests.test_discovery_screening_assessment import source as raw_source,row

def source(rows):
    a=raw_source(rows)
    import hashlib
    a["listing_segments"][0]["evidence_sha256"]=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
    return a


@pytest.fixture
def ledger():
    e=create_engine('sqlite:///:memory:');install(e);clock=[1000.0];l=Ledger(e,clock=lambda:clock[0])
    yield l,clock
    e.dispose()


def task(l,*,ref='TEST/26',state='QUEUED',reason=None,dependencies=(),task='SCREENING',contract='fixture',**kw):
    return l.enqueue(dict(kind='APPLICATION',council='manchester',reference=ref),task,contract=contract,state=state,reason=reason,dependencies=dependencies,**kw)


def grant(l,keys,**kw):
    contracts={l.get(k)['contract'] for k in keys};l.grant('INGESTION_TEST_one',keys,expires_at=100000,contracts=contracts,**kw)


def outer():return dict(exit_code=0,cleanup='CLOSED',live_owned_survivors=0,expired=False,limit_hit=None,peak_owned_rss=1000,elapsed_seconds=1)

def claim(l,k):return l.claim(k,'worker','INGESTION_TEST_one')


def test_additive_migration_idempotent_empty_rollback_and_no_base_startup(ledger):
    l,_=ledger;install(l.engine)
    assert set(inspect(l.engine).get_table_names())=={'ingestion_work_items','ingestion_work_attempts'}
    from app.db.models import Base
    assert not set(metadata.tables)&set(Base.metadata.tables)
    uninstall_empty(l.engine);assert inspect(l.engine).get_table_names()==[]
    install(l.engine);task(l)
    with pytest.raises(ValueError,match='PRESERVE'):uninstall_empty(l.engine)


def test_idempotent_task_identity_not_application_and_independent_states(ledger):
    l,_=ledger;k=task(l);assert task(l)==k
    second=task(l,task='FACTUAL_REFRESH')
    assert second!=k;grant(l,[k,second]);c=claim(l,k);l.checkpoint(c,{'fixture':'retained'});l.finish(c,{'outcome':'INSUFFICIENT_EVIDENCE'})
    assert l.get(k)['state']=='COMPLETE' and l.get(second)['state']=='QUEUED'
    assert 'applications' not in inspect(l.engine).get_table_names()


def test_permissions_dependencies_eligibility_and_exhaustion(ledger):
    l,clock=ledger;a=task(l);b=task(l,ref='OTHER',dependencies=[a],eligible_at=2000,max_attempts=1)
    with pytest.raises(Denied):claim(l,a)
    grant(l,[a,b]);c=claim(l,a)
    with pytest.raises(Denied):claim(l,b)
    l.finish(c,{'outcome':'COMPLETE'});clock[0]=2001;c=claim(l,b)
    with pytest.raises(Denied):claim(l,b)
    l.finish(c,{},state='DEFERRED',reason='TEST',delay=1);clock[0]+=2
    with pytest.raises(Denied):claim(l,b)


@pytest.mark.parametrize('state',['UNSUPPORTED_CONTRACT','SAFETY_BLOCKED','PERSISTENCE_UNCERTAIN'])
def test_blocked_never_runs_after_time_or_grant(ledger,state):
    l,clock=ledger;k=task(l,state=state,reason='REVIEW_REQUIRED');grant(l,[k]);clock[0]+=999
    with pytest.raises(Denied):claim(l,k)


def test_historical_authority_and_production_engines_rejected(ledger):
    l,_=ledger;k=task(l)
    with pytest.raises(Denied):l.grant('AUTHORISE_METADATA_13_SEQUENTIAL_20261016_ONCE',[k],contracts=['fixture'],expires_at=2000)
    e=create_engine('sqlite:////tmp/not-a-disposable-database.db')
    with pytest.raises(Denied):Ledger(e)
    assert not Path('/tmp/not-a-disposable-database.db').exists()
    e.dispose()


def test_checkpoint_crash_resume_fences_old_worker(ledger):
    l,clock=ledger;k=task(l);grant(l,[k]);old=claim(l,k);l.checkpoint(old,{'evidence':'retained'})
    clock[0]+=121;l.recover(old,cleanup_closed=True);new=claim(l,k)
    assert l.get(k)['checkpoint']=={'evidence':'retained'} and new.fence>old.fence
    for operation in [lambda:l.checkpoint(old,{}),lambda:l.finish(old,{}),lambda:l.intent(old,'writes')]:
        with pytest.raises(StaleClaim):operation()
    l.finish(new,{'outcome':'RESUMED_WITHOUT_SOURCE'})
    with l.engine.connect() as c:assert c.scalar(select(func.count()).select_from(A))==2


@pytest.mark.parametrize('operation,state',[('source_calls','SAFETY_BLOCKED'),('writes','PERSISTENCE_UNCERTAIN')])
def test_expired_intent_is_not_replay_permission(ledger,operation,state):
    l,clock=ledger;k=listing_task(l) if operation=='source_calls' else task(l,task='FACTUAL_REFRESH');other=task(l,ref='OTHER');grant(l,[k,other],source_calls=1,writes=1)
    c=claim(l,k);l.intent(c,operation);clock[0]+=121;l.recover(c,cleanup_closed=True)
    assert l.get(k)['state']==state
    with pytest.raises(Denied):claim(l,k)
    if operation=='writes':
        with pytest.raises(Denied):claim(l,other)


def test_write_intent_cannot_be_cleared_by_checkpoint_or_finish(ledger):
    l,_=ledger;k=task(l,task='FACTUAL_REFRESH');other=task(l,ref='OTHER');grant(l,[k,other],writes=1);c=claim(l,k);l.intent(c,'writes')
    with pytest.raises(Denied):l.checkpoint(c,{})
    with pytest.raises(Denied):l.finish(c,{})
    with pytest.raises(Denied):claim(l,other)
    count=[]
    def lost(_):count.append('committed-external-effect');raise RuntimeError('lost ack')
    with pytest.raises(UncertainPersistence):l.fenced_effect(c,lost)
    assert len(count)==1
    with pytest.raises(Denied):claim(l,other)


def test_concurrent_claim_one_owner_file_sqlite():
    import tempfile,os
    fd,p=tempfile.mkstemp(prefix='ingestion-test-',suffix='.db');os.close(fd)
    e=create_engine('sqlite:///'+p,connect_args={'timeout':3});install(e);l=Ledger(e);k=task(l);l.grant('INGESTION_TEST_one',[k],expires_at=time.time()+60,contracts=['fixture'])
    barrier=Barrier(2)
    def run(i):
        barrier.wait()
        try:return l.claim(k,'worker'+str(i),'INGESTION_TEST_one')
        except Denied:return None
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,[1,2]))
        assert sum(x is not None for x in results)==1
    finally:e.dispose();os.unlink(p)


def listing_task(l,cfg=SCREENING_CONFIG):
    return l.enqueue(dict(kind='DISCOVERY_SCOPE',council=cfg.council,start=cfg.start,end=cfg.end,semantics='VALIDATED'),'LISTING_METADATA',contract='fixture-listing')


def test_listing_to_screening_crash_dedup_citations_and_no_details(ledger):
    l,_=ledger;k=listing_task(l);grant(l,[k]);co=Coordinator(l,{'fixture-listing':ListingContract('fixture-listing',SCREENING_CONFIG,SCREENING_CASE)})
    c=claim(l,k);audit=source([row('Discharge of condition attached to planning permission 144426/FO/2025')]);children=co.listing(c,audit)
    assert len(children)==1 and l.get(k)['checkpoint']['records']==audit['listing_records']
    # Completion does not grant execution permission to the newly retained child.
    with pytest.raises(Denied):claim(l,children[0])
    l.grant('INGESTION_TEST_screen',children,expires_at=2000,contracts=['listing-screen-v1'])
    sc=l.claim(children[0],'screener','INGESTION_TEST_screen');result=co.screening(sc)
    assert result['disposition']=='RELATED_APPLICATION_FOLLOW_THROUGH'
    citation=result['citations']['occurrences'][0];assert citation['literal']=='144426/FO/2025' and citation['target_council'] is None
    assert task(l,ref='OTHER') # queue retention doesn't require applications table
    assert l.get(children[0])['state']=='COMPLETE'


def test_interruption_after_listing_checkpoint_materializes_once(ledger):
    l,clock=ledger;k=listing_task(l);grant(l,[k]);co=Coordinator(l,{'fixture-listing':ListingContract('fixture-listing',SCREENING_CONFIG,SCREENING_CASE)});old=claim(l,k)
    co._listing(old,source([row()]));clock[0]+=121;l.recover(old,cleanup_closed=True);new=claim(l,k)
    children=co.resume_listing(new);assert len(children)==1
    with l.engine.connect() as c:assert c.scalar(select(func.count()).select_from(W))==3 # control,parent,child
    with pytest.raises(Denied):co.resume_listing(old)


def test_historical_and_current_windows_share_exact_components(ledger):
    from dataclasses import replace
    from verification.discovery.arcus_ui_window import qualify_segment
    l,_=ledger;cfg2=replace(dated_config(SCREENING_CONFIG,'2026-10-16','2026-10-16'))
    for i,cfg in enumerate([SCREENING_CONFIG,cfg2]):
        k=l.enqueue(dict(kind='DISCOVERY_SCOPE',council=cfg.council,start=cfg.start,end=cfg.end,semantics='VALIDATED'),'DISCOVERY',contract='window'+str(i))
        l.grant('INGESTION_TEST_window'+str(i),[k],expires_at=2000,contracts=['window'+str(i)])
        c=l.claim(k,'worker','INGESTION_TEST_window'+str(i));a=source([row()])
        if i:
            old=a['listing_records'][0];card=dict(fields=[dict(label='Reference',value=old['reference']),dict(label='Valid Date',value='16/10/2026')],links=[dict(text=old['reference'],href=old['source_url'])],assessment_capture=old['assessment_capture'])
            a['listing_records']=qualify_segment('Showing 1 to 1 of 1 results',[card],1,config=cfg)[3];a.update(destination=cfg.destination,applied_interval=[cfg.start,cfg.end],requested_interval=[cfg.start,cfg.end])
        import hashlib
        a['listing_segments'][0]['evidence_sha256']=hashlib.sha256(json.dumps(a['listing_records'],sort_keys=True).encode()).hexdigest()
        co=Coordinator(l,{'window'+str(i):ListingContract('window'+str(i),cfg,SCREENING_CASE)})
        assert len(co.listing(c,a))==1


def test_reviewed_local_failure_allows_unrelated_work_global_does_not(ledger):
    l,_=ledger;a=listing_task(l);b=task(l,ref='OTHER');grant(l,[a,b],source_calls=1);co=Coordinator(l,{},isolated_contracts={'fixture-listing'})
    c=claim(l,a);l.intent(c,'source_calls');co.fail(c,'RATE_LIMIT',cleanup_closed=True,accounting_complete=True,council_isolated=True,source_audit=source([row()]),outer=outer())
    assert l.get(a)['state']=='DEFERRED';other=claim(l,b);l.finish(other,{})
    # ConsumedSalford category is deliberately not a retryable local category.
    l.stop('SALFORD_TARGET_CLOSED_CONSUMED_AUTHORITY')
    with pytest.raises(Denied):claim(l,a)


def test_source_receipt_requires_closed_outer_and_no_checkpoint_replay(ledger):
    l,_=ledger;k=listing_task(l);grant(l,[k],source_calls=1);co=Coordinator(l,{'fixture-listing':ListingContract('fixture-listing',SCREENING_CONFIG,SCREENING_CASE)})
    c=claim(l,k)
    with pytest.raises(Denied):co.source(c,lambda _: (source([row()]),{'cleanup':'UNKNOWN'}))
    with pytest.raises(Denied):claim(l,k)


def test_evidence_bound_and_unqualified_identity(ledger):
    l,_=ledger;k=listing_task(l);grant(l,[k]);c=claim(l,k)
    with pytest.raises(Denied):l.checkpoint(c,{'large':'x'*(128*1024)})
    co=Coordinator(l,{'fixture-listing':ListingContract('fixture-listing',SCREENING_CONFIG,SCREENING_CASE)})
    a=source([row()]);a['listing_records'][0]['source_url']=a['listing_records'][0]['source_url'].replace('arcusbe.manchester.gov.uk','wrong.invalid')
    with pytest.raises(ValueError):co.listing(c,a)


def test_priority_dispatch_and_bound_retry_permission(ledger):
    l,clock=ledger;low=task(l,ref='LOW',priority=1);high=task(l,ref='HIGH',priority=99);grant(l,[low,high],source_calls=1)
    chosen=l.claim_next('worker','INGESTION_TEST_one');assert chosen.key==high
    co=Coordinator(l,{},isolated_contracts={'fixture'});co.fail(chosen,'RATE_LIMIT',cleanup_closed=True,accounting_complete=True,council_isolated=True,source_audit=source([row()]),outer=outer())
    assert l.get(high)['eligible_at']==clock[0]+3600
    clock[0]+=3601;new=l.claim_next('next','INGESTION_TEST_one');assert new.key==high
    with pytest.raises(Denied,match='TASK_OPERATION'):l.intent(new,'source_calls')


@pytest.mark.parametrize('change',[{'peak_owned_rss':-1},{'peak_owned_rss':True},{'supervisor_seconds':float('nan')},{'requests':True}])
def test_typed_source_resource_rejection(ledger,change):
    l,_=ledger;k=listing_task(l);grant(l,[k]);co=Coordinator(l,{'fixture-listing':ListingContract('fixture-listing',SCREENING_CONFIG,SCREENING_CASE)})
    with pytest.raises(ValueError):co.listing(claim(l,k),dict(source([row()]),**change))


def test_attempt_outcome_and_resource_limits_are_not_borrowed(ledger):
    l,_=ledger;limits=dict(DEFAULT_LIMITS,requests=1);k=listing_task(l)
    k2=l.enqueue(dict(kind='DISCOVERY_SCOPE',council='manchester',start=SCREENING_CONFIG.start,end=SCREENING_CONFIG.end,semantics='VALIDATED'),'DISCOVERY',contract='fixture-listing',limits=limits)
    grant(l,[k,k2]);co=Coordinator(l,{'fixture-listing':ListingContract('fixture-listing',SCREENING_CONFIG,SCREENING_CASE)})
    with pytest.raises(Denied,match='RESOURCE'):co.listing(claim(l,k2),source([row()]))


def test_retained_manchester14_enters_same_coordinator_without_source(ledger):
    l,_=ledger
    archive=Path(__file__).parent/'fixtures/ingestion/manchester14.json'
    # Exact accepted checkpoint from evidence commit; no source observation.
    raw=archive.read_bytes()
    import hashlib
    assert hashlib.sha256(raw).hexdigest()=='b486cea799886fd4317e18241a4ea6615969a27012b7de3af98be9ab395b2210'
    k=listing_task(l);grant(l,[k]);co=Coordinator(l,{'fixture-listing':ListingContract('fixture-listing',SCREENING_CONFIG,SCREENING_CASE)})
    children=co.listing(claim(l,k),json.loads(raw));assert len(children)==14
    assert l.get(k)['checkpoint']['records']==json.loads(raw)['listing_records']


def test_application_metadata_from_scope_reuses_capture_without_refetch(ledger):
    l,_=ledger;scope=listing_task(l);grant(l,[scope]);co=Coordinator(l,{'fixture-listing':ListingContract('fixture-listing',SCREENING_CONFIG,SCREENING_CASE)})
    first=co.listing(claim(l,scope),source([row()]))
    app=l.enqueue(dict(kind='APPLICATION',council='manchester',reference='TEST/26'),'LISTING_METADATA',contract='retained-scope-match-v1',dependencies=[scope])
    l.grant('INGESTION_TEST_match',[app],expires_at=2000,contracts=['retained-scope-match-v1'])
    out=co.metadata_from_scope(l.claim(app,'matcher','INGESTION_TEST_match'))
    assert out==first and l.get(app)['state']=='COMPLETE'


@pytest.mark.parametrize('outer',[dict(exit_code=1,cleanup='CLOSED',live_owned_survivors=0,expired=False,limit_hit=None,peak_owned_rss=1,elapsed_seconds=1),dict(exit_code=0,cleanup='CLOSED',live_owned_survivors=0,expired=False,limit_hit=None,peak_owned_rss=-1,elapsed_seconds=1)])
def test_failed_or_negative_outer_receipt_never_reusable(ledger,outer):
    l,_=ledger;k=listing_task(l);grant(l,[k],source_calls=1);co=Coordinator(l,{'fixture-listing':ListingContract('fixture-listing',SCREENING_CONFIG,SCREENING_CASE)})
    with pytest.raises(Denied):co.source(claim(l,k),lambda _: (source([row()]),outer))
    assert l.get(k)['checkpoint'] is None


def test_source_preflight_and_retained_path_cannot_bypass_intent(ledger):
    l,_=ledger;wrong=task(l);k=listing_task(l);grant(l,[wrong,k],source_calls=1)
    co=Coordinator(l,{'fixture-listing':ListingContract('fixture-listing',SCREENING_CONFIG,SCREENING_CASE)});called=[]
    with pytest.raises(Denied):co.source(claim(l,wrong),lambda _:called.append('called'))
    assert not called
    c=claim(l,k);l.intent(c,'source_calls')
    with pytest.raises(Denied,match='RETAINED_PATH'):co.listing(c,source([row()]))
    assert l.get(k)['phase']=='SOURCE_INTENT'


def test_source_stage_reserves_once_and_persists_closed_receipt(ledger):
    l,_=ledger;k=listing_task(l);grant(l,[k],source_calls=1)
    co=Coordinator(l,{'fixture-listing':ListingContract('fixture-listing',SCREENING_CONFIG,SCREENING_CASE)})
    calls=[]
    def reader(_):calls.append(1);return source([row()]),outer()
    c=claim(l,k);children=co.source(c,reader)
    assert len(children)==1 and len(calls)==1
    assert l.get(k)['checkpoint']['outer_supervisor']['cleanup']=='CLOSED'
    with pytest.raises(Denied):co.source(c,reader)
    assert len(calls)==1
