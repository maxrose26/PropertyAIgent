"""Existing non-superuser disposable PG17 fixture; no production connections."""
import copy,json
from contextlib import contextmanager
import pytest
from tests.test_database_evidence_migration_pg import migration_world,installed,world,support
from verification.ingestion_storage import owner_pilot as p,owner_pilot_continuation as step,intake_owner as op
from verification.ingestion_storage.database_evidence import migration_sql,OWNER_SQL,verify_inventory

@pytest.mark.parametrize('mode',['success','rollback','wrong_definition'])
def test_exact_namespace_transition_and_rollback(migration_world,monkeypatch,mode):
    boot=migration_world['boot']
    with support.actor() as c:support.execute(c,migration_sql())
    old=OWNER_SQL.split('REVOKE ALL ON FUNCTION',1)[0].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1).replace(",'b-dbpilot-20261027-1102-04_owner'","")
    boot.execute(old)
    before=op.ledger_sha(boot);members=boot.execute(op.MEMBERS).fetchall()
    q='SELECT * FROM ingestion_intake_owner_state(%s,%s,%s,%s)'
    oldj=p.Journal(None,p.PREDECESSOR)
    with support.actor() as c:c.execute(q,(oldj.owner_period,oldj.owner_run,'',b'PRESERVED_ENCRYPTED_FIXTURE'))
    if mode=='wrong_definition':boot.execute(old.replace('OWNER_STATE_OWNER_ONLY','WRONG_OWNER_STATE_OWNER_ONLY'))
    body=boot.execute("SELECT prosrc FROM pg_proc WHERE proname='ingestion_intake_owner_state'").fetchone()[0]
    if mode=='rollback':monkeypatch.setattr(step,'verify_inventory',lambda _:(_ for _ in ()).throw(RuntimeError('SYNTHETIC_LATE_FAILURE')))
    with support.actor() as c:
        if mode=='success':step.migrate_owner_namespace(c);step.migrate_owner_namespace(c)
        else:
            with pytest.raises((op.Denied,RuntimeError)):step.migrate_owner_namespace(c)
        assert c.execute(q,(oldj.owner_period,oldj.owner_run,'',None)).fetchone()[1]==b'PRESERVED_ENCRYPTED_FIXTURE'
        if mode=='success':assert c.execute(q,(p.OWNER_PERIOD,p.OWNER_RUN,'',None)).fetchall()==[]
        else:assert c.execute("SELECT prosrc FROM pg_proc WHERE proname='ingestion_intake_owner_state'").fetchone()[0]==body
    assert op.ledger_sha(boot)==before and boot.execute(op.MEMBERS).fetchall()==members and support.actor_flags()==(False,False,False)

def test_actual_restricted_qualification_driver_budget_and_close(migration_world,monkeypatch,record_property):
    from verification.ingestion_storage import operational_controller as runtime,intake_owner_operations as extra,tls_trust
    from sqlalchemy.engine import URL,make_url
    boot=migration_world['boot']
    with support.actor() as c:support.execute(c,migration_sql())
    boot.execute('GRANT ingestion_barrier_releaser TO postgres WITH ADMIN TRUE,INHERIT FALSE,SET FALSE GRANTED BY provisioning_bootstrap')
    e={'revision':'1'*40,'workflow_sha256':'2'*64,'manifest_sha256':'3'*64};release={'execution_binding':e,'deployment':'dep-'+'a'*20}
    monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(release))
    profile=p.source_profile({'execution_binding':e,'browser_canary':'LAUNCHED_AND_CLOSED','browser_path':'/fixture/browser','browser_sha256':'a'*64},e['revision'])
    b,policy=p.fixed_binding(release,profile,'192.0.2.1','a'*64);journal={'version':'FINITE_INTAKE_PERIOD_V1','state':'ARMED_NO_RETRY','binding':b,'policy':policy}
    with support.actor() as c:extra.issue_period(c,b,policy,journal,lambda _:None)
    state=[]
    with support.actor() as c:op.activate(c,b,lambda v:state.append(copy.deepcopy(v)))
    pilot=object.__new__(p.Pilot);pilot.state={'binding':b,'access':state[-1]};budgets=[]
    RealBudget=runtime.DatabaseBudget
    # Only endpoint/TLS mapping is synthetic. Budget, driver, qualification SQL,
    # server timeouts, role identity, finite activation and close are real PG17.
    monkeypatch.setattr(p,'url',lambda route,role,password:URL.create('postgresql+psycopg',username=role,password=password,host='127.0.0.1',port=5432,database='postgres').render_as_string(hide_password=False))
    monkeypatch.setattr(runtime,'runtime_principal',lambda raw,*args:(make_url(raw),make_url(raw).username))
    class Budget(RealBudget):
        def __init__(self,**kw):super().__init__(**kw);budgets.append(self)
        def engine(self,raw,**kw):
            assert kw['route']=='POOLER' and kw['ssl']['sslmode']=='verify-full'
            return super().engine(raw,ssl=None)
    monkeypatch.setattr(runtime,'DatabaseBudget',Budget)
    try:
        result=pilot.qualify()
        assert len(result)==2 and all(x['attempts']==1 and x['closed'] for x in result)
        assert all(x.statements<=20 and all(c.closed for c in x.opened) for x in budgets)
        record_property('actual_qualification_driver_statements',[x.statements for x in budgets])
        record_property('postgres_version',migration_world['server_version'])
    finally:
        with support.actor() as c:receipt=op.close(c,state[-1],lambda v:state.append(copy.deepcopy(v)))
        assert receipt['runtime_access']=='DISABLED' and receipt['sessions']=='ABSENT' and receipt['temporary_owner']=='REMOVED'
