"""Fixed disposable PG only. Real ledger migration/locks and real shared B2 writer."""
import os,time,json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import create_engine,select,text,inspect,func
from sqlalchemy.orm import Session
from app.ingestion.schema import install,uninstall_empty,metadata,WorkItem as W,WorkAttempt as A
from app.ingestion.ledger import Ledger,Denied,StaleClaim,UncertainPersistence
from app.ingestion.coordinator import Coordinator,FactualContract
from app.db.models import Base,Council,Application
from tests.test_discovery_ingestion_ledger import task


@pytest.fixture
def pg():
    raw=os.environ.get('DISCOVERY_TEST_POSTGRES_URL')
    if not raw:pytest.skip('fixed disposable PostgreSQL service required')
    from sqlalchemy.engine import make_url
    u=make_url(raw)
    if (u.host,u.port,u.database,u.username)!=('127.0.0.1',5432,'stage4_discovery_test','discovery_test'):raise ValueError('DISPOSABLE_ONLY')
    e=create_engine(u,connect_args={'connect_timeout':3,'options':'-c statement_timeout=10000 -c lock_timeout=3000'},pool_size=5,max_overflow=0,pool_timeout=3)
    install(e);Base.metadata.create_all(e)
    try:yield e
    finally:
        metadata.drop_all(e);Base.metadata.drop_all(e);e.dispose()


def allowance(l,keys,*,writes=0):
    l.grant('INGESTION_TEST_pg',keys,contracts=[l.get(k)['contract'] for k in keys],expires_at=l.clock()+3600,writes=writes)


def test_pg_migration_idempotent_constraints_rls_and_rollback(pg):
    install(pg)
    with pg.connect() as c:
        flags=c.execute(text("SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname IN ('ingestion_work_items','ingestion_work_attempts')")).all()
        assert len(flags)==2 and all(a and b for _,a,b in flags)
        assert c.scalar(text("SELECT count(*) FROM pg_policies WHERE tablename IN ('ingestion_work_items','ingestion_work_attempts')"))==0
        assert not c.scalar(text("SELECT count(*) FROM pg_class r, LATERAL aclexplode(r.relacl) a WHERE r.relname='ingestion_work_items' AND a.grantee=0"))
    uninstall_empty(pg);assert not inspect(pg).has_table('ingestion_work_items');install(pg)
    l=Ledger(pg);task(l)
    with pytest.raises(ValueError,match='PRESERVE'):uninstall_empty(pg)


def test_pg_concurrent_claim_and_fenced_recovery(pg):
    clock=[1000.0];l=Ledger(pg,clock=lambda:clock[0]);k=task(l,task='FACTUAL_REFRESH');allowance(l,[k],writes=1);barrier=Barrier(2)
    def one(i):
        barrier.wait()
        try:return l.claim(k,'worker'+str(i),'INGESTION_TEST_pg')
        except Denied:return None
    with ThreadPoolExecutor(max_workers=2) as p:results=list(p.map(one,[1,2]))
    claims=[x for x in results if x];assert len(claims)==1;old=claims[0]
    l.checkpoint(old,{'retained':'receipt'});clock[0]+=121;l.recover(old,cleanup_closed=True);new=l.claim(k,'new','INGESTION_TEST_pg')
    with pytest.raises(StaleClaim):l.intent(old,'writes')
    l.finish(new,{'outcome':'RESUMED'})


def fixture_app(engine):
    from tests.test_arcus_b2_adapter import payload,encode
    from verification.direct_reference.arcus_adapter import from_response,representative_row
    from app.config import CouncilConfig
    row=representative_row('manchester')
    with Session(engine) as s:
        s.add(Council(code='manchester',name='Manchester',base_url='https://arcusbe.manchester.gov.uk',date_field_mode='validated',doc_system='arcus'))
        s.add(Application(id=row['application_id'],council_code='manchester',reference=row['reference'],status='Awaiting decision'));s.commit()
    config=CouncilConfig(code='manchester',name='Manchester',base_url=row['source_url'],date_field_mode='validated',doc_system='arcus',anite_base_url=None,unit_threshold=10,region='GM',country='England')
    return row,from_response('manchester',encode(payload())),config


def test_real_b2_write_readback_and_resume_without_repeated_effect(pg,monkeypatch):
    row,obs,council=fixture_app(pg);clock=[1000.0];l=Ledger(pg,clock=lambda:clock[0])
    k=task(l,ref=row['reference'],task='FACTUAL_REFRESH',contract='B2_EXISTING_COUPLED_V1');allowance(l,[k],writes=1)
    co=Coordinator(l,{'B2_EXISTING_COUPLED_V1':FactualContract('B2_EXISTING_COUPLED_V1',row)});claim=l.claim(k,'worker','INGESTION_TEST_pg')
    original=l.finish
    def crash(*a,**kw):raise RuntimeError('crash after writer+readback checkpoint before acknowledgement')
    monkeypatch.setattr(l,'finish',crash)
    with pytest.raises(RuntimeError,match='crash'):co.factual_refresh(claim,council=council,observation=obs,accepted_row=row)
    assert l.get(k)['phase']=='CHECKPOINTED' and l.get(k)['checkpoint']['outcome']=='SUPPORTED_FACTS_VERIFIED'
    with Session(pg) as s:
        a=s.get(Application,row['application_id']);assert a.decision=='Approve';stamp=a.status_verified_at
    clock[0]+=121;l.recover(claim,cleanup_closed=True);new=l.claim(k,'recovered','INGESTION_TEST_pg');monkeypatch.setattr(l,'finish',original)
    out=co.factual_refresh(new,council=council,observation=obs,accepted_row=row)
    assert out['outcome']=='SUPPORTED_FACTS_VERIFIED' and l.get(k)['state']=='COMPLETE'
    with Session(pg) as s:
        assert s.get(Application,row['application_id']).status_verified_at==stamp
        assert s.scalar(select(func.count()).select_from(Application))==1
    with pytest.raises(Denied):l.claim(k,'duplicate','INGESTION_TEST_pg')


def test_real_commit_lost_ack_blocks_all_subsequent_writes(pg):
    row,obs,council=fixture_app(pg);l=Ledger(pg);k=task(l,ref=row['reference'],task='FACTUAL_REFRESH');other=task(l,ref='OTHER');allowance(l,[k,other],writes=2)
    claim=l.claim(k,'worker','INGESTION_TEST_pg');l.intent(claim,'writes')
    def lost(_):
        with Session(pg) as s:
            s.get(Application,row['application_id']).address='DISPOSABLE_EFFECT';s.commit()
        raise RuntimeError('lost acknowledgement after actual commit')
    with pytest.raises(UncertainPersistence):l.fenced_effect(claim,lost)
    assert l.get(k)['phase']=='WRITE_INTENT'
    with pytest.raises(Denied):l.claim(other,'other','INGESTION_TEST_pg')
    with Session(pg) as s:assert s.get(Application,row['application_id']).address=='DISPOSABLE_EFFECT'


def test_shared_admission_duplicate_delivery_no_duplicate_application(pg):
    from app.pipeline.discovery_admission import admit_identity
    from tests.test_discovery_admission import envelope
    with Session(pg) as s:
        s.add(Council(code='bolton',name='Bolton',base_url='https://paplanning.bolton.gov.uk',date_field_mode='received',doc_system='idox'));s.commit()
    barrier=Barrier(2)
    def one(_):barrier.wait();return admit_identity(pg,envelope())
    with ThreadPoolExecutor(max_workers=2) as p:results=list(p.map(one,[1,2]))
    assert {r['outcome'] for r in results}=={'CREATED_PENDING','ALREADY_KNOWN'}
    with Session(pg) as s:assert s.scalar(select(func.count()).select_from(Application))==1


def test_pg_shared_listing_screening_selective_b2_path(pg):
    from app.ingestion.coordinator import ListingContract
    from verification.discovery.arcus_ui_config import SCREENING_CONFIG,SCREENING_CASE
    from verification.discovery.arcus_ui_window import qualify_segment
    from tests.test_discovery_ingestion_ledger import listing_task,source,row as listing_row
    row,obs,council=fixture_app(pg);l=Ledger(pg)
    parent=listing_task(l);allowance(l,[parent])
    raw=listing_row('Erection of 49 dwellings')
    card=dict(fields=[dict(label='Reference',value=row['reference']),dict(label='Valid Date',value='02/10/2026')],links=[dict(text=row['reference'],href=row['source_url'])],assessment_capture=raw['assessment_capture'])
    record=qualify_segment('Showing 1 to 1 of 1 results',[card],1,config=SCREENING_CONFIG)[3][0]
    co=Coordinator(l,{'fixture-listing':ListingContract('fixture-listing',SCREENING_CONFIG,SCREENING_CASE),'B2_EXISTING_COUPLED_V1':FactualContract('B2_EXISTING_COUPLED_V1',row)})
    screen_key=co.listing(l.claim(parent,'discover','INGESTION_TEST_pg'),source([record]))[0]
    l.grant('INGESTION_TEST_screen',[screen_key],contracts=['listing-screen-v1'],expires_at=time.time()+600)
    screen=co.screening(l.claim(screen_key,'screen','INGESTION_TEST_screen'))
    assert screen['disposition']=='SUPPORTED_PROCESSING_PRIORITY'
    fact=task(l,ref=row['reference'],task='FACTUAL_REFRESH',contract='B2_EXISTING_COUPLED_V1',dependencies=[screen_key])
    with pytest.raises(Denied):l.claim(fact,'unauthorised','INGESTION_TEST_screen')
    l.grant('INGESTION_TEST_fact',[fact],contracts=['B2_EXISTING_COUPLED_V1'],expires_at=time.time()+600,writes=1)
    result=co.factual_refresh(l.claim(fact,'facts','INGESTION_TEST_fact'),council=council,observation=obs,accepted_row=row)
    assert result['outcome']=='SUPPORTED_FACTS_VERIFIED' and result['identity']=='EXISTING_IDENTITY_PRESERVED'
    assert all(l.get(k)['state']=='COMPLETE' for k in [parent,screen_key,fact])


def test_pg_unsupported_facts_withheld_before_write(pg):
    from tests.test_arcus_b2_adapter import payload,encode
    from verification.direct_reference.arcus_adapter import from_response
    row,_,council=fixture_app(pg);obs=from_response('manchester',encode(payload(decision=None)))
    l=Ledger(pg);k=task(l,ref=row['reference'],task='FACTUAL_REFRESH',contract='B2_EXISTING_COUPLED_V1');allowance(l,[k],writes=0)
    co=Coordinator(l,{'B2_EXISTING_COUPLED_V1':FactualContract('B2_EXISTING_COUPLED_V1',row)})
    co.factual_refresh(l.claim(k,'facts','INGESTION_TEST_pg'),council=council,observation=obs,accepted_row=row)
    assert l.get(k)['state']=='UNSUPPORTED_CONTRACT' and l.get(k)['outcome']['outcome']=='FACTS_WITHHELD'
    with Session(pg) as s:assert s.get(Application,row['application_id']).status=='Awaiting decision'
