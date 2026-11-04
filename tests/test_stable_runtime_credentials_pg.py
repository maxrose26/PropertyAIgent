"""Actual existing non-superuser PG17 fixture, stable and legacy cleanup."""
import copy,json
from types import SimpleNamespace
from sqlalchemy.engine import URL,make_url
import pytest
from tests.test_database_evidence_migration_pg import migration_world,installed,world,support
from verification.ingestion_storage import owner_pilot as p,intake_owner as op,intake_owner_operations as extra,stable_runtime_credentials as stable,operational_controller as driver
from verification.ingestion_storage.database_evidence import migration_sql
from verification.ingestion_storage.runtime_authentication import qualify
from verification.ingestion_storage.intake_budget import IntakeRun,LIMITS

@pytest.mark.parametrize('mode',['stable','rollback','legacy','interface_mismatch'])
def test_actual_stable_configuration_qualification_and_cleanup(migration_world,monkeypatch,record_property,mode):
    boot=migration_world['boot']
    with support.actor() as c:support.execute(c,migration_sql())
    members=boot.execute(op.MEMBERS).fetchall();ledger=op.ledger_sha(boot)
    if mode!='legacy':
        with support.actor() as c:value=stable.prepare(c)
        if mode=='rollback':
            real=stable.hashes;monkeypatch.setattr(stable,'hashes',lambda c:{})
            with support.actor() as c:
                with pytest.raises(op.Denied,match='PRESERVATION'):stable.configure(c,value)
                op.dormant(c)
            assert op.ledger_sha(boot)==ledger and boot.execute(op.MEMBERS).fetchall()==members
            return
        with support.actor() as c:
            configured=stable.configure(c,value);assert configured['password_verifiers']=='RETAINED'
            op.dormant(c,stable_verifiers=value['verifier_sha256'])
            with pytest.raises(op.Denied):stable.configure(c,value)
    boot.execute('GRANT ingestion_barrier_releaser TO postgres WITH ADMIN TRUE,INHERIT FALSE,SET FALSE GRANTED BY provisioning_bootstrap')
    e={'revision':'1'*40,'workflow_sha256':'2'*64,'manifest_sha256':'3'*64};release={'execution_binding':e,'deployment':'dep-'+'a'*20}
    monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(release))
    profile=p.source_profile({'execution_binding':e,'browser_canary':'LAUNCHED_AND_CLOSED','browser_path':'/fixture/browser','browser_sha256':'a'*64},e['revision'])
    b,policy=p.fixed_binding(release,profile,'192.0.2.1','a'*64)
    if mode in ('stable','interface_mismatch'):b.update(credential_policy='STABLE_RESTRICTED_V1',credential_verifier_sha256=value['verifier_sha256'])
    with support.actor() as c:extra.issue_period(c,b,policy,{'version':'FINITE_INTAKE_PERIOD_V1','state':'ARMED_NO_RETRY','binding':b,'policy':policy},lambda _:None)
    state=[]
    with support.actor() as c:
        prepared=op.prepare_activation(c,b,stable_credentials=value['passwords'] if mode in ('stable','interface_mismatch') else None)
        op.activate(c,b,lambda v:state.append(copy.deepcopy(v)),prepared=prepared)
    if mode in ('stable','interface_mismatch'):
        with support.actor() as c:assert stable.hashes(c)==value['verifier_sha256']
    runtime=SimpleNamespace(args=SimpleNamespace(period=p.PERIOD),binding=e,run=IntakeRun(),options={'ssl':{'sslmode':'verify-full'},'route':'POOLER','hostaddr':'192.0.2.1'},emit=lambda *_:None)
    runtime.urls={role:URL.create('postgresql+psycopg',username=role,password=state[-1]['passwords'][role],host='127.0.0.1',port=5432,database='postgres').render_as_string(hide_password=False) for role in op.ROLES}
    monkeypatch.setattr(driver,'runtime_principal',lambda raw,*args:(make_url(raw),make_url(raw).username))
    class Budget(driver.DatabaseBudget):
        def engine(self,url,**kw):return super().engine(url,ssl=None)
    acl=boot.execute("SELECT proacl::text FROM pg_proc WHERE oid='public.ingestion_intake_evidence_write(text,text,text,bytea)'::regprocedure").fetchone()
    if mode=='interface_mismatch':boot.execute('REVOKE EXECUTE ON FUNCTION public.ingestion_intake_evidence_write(text,text,text,bytea) FROM ingestion_worker')
    try:
        receipt=qualify(runtime,b['valid_until'],budget_factory=Budget)
        if mode=='interface_mismatch':
            assert receipt['status']=='REFUSED' and receipt['source_requests']==0 and len(receipt['attempts'])==1
            comparison=receipt['first_qualification_failure']['comparison']
            assert comparison['first_mismatch']=='evidence_write_execute' and comparison['checks']['evidence_write_execute'] is False
            record_property('native_mismatch',comparison['first_mismatch'])
            return
        assert receipt['status']=='VERIFIED_BOTH_RESTRICTED_ROLES',receipt
        assert all(a['profile_comparison']['status']=='MATCH' for a in receipt['attempts'])
        assert len(receipt['roles'])==2 and runtime.run.totals()['connection_attempts']==2
        assert runtime.run.totals()['driver_statements']==sum(a['driver_statements'] for a in receipt['attempts'])
        assert runtime.run.totals()['all_connections_closed'] and LIMITS['driver_statements']==2080 and LIMITS['wall_seconds']==960
        record_property('actual_qualification_statements',[a['driver_statements'] for a in receipt['attempts']])
    finally:
        if mode=='interface_mismatch':
            boot.execute('GRANT EXECUTE ON FUNCTION public.ingestion_intake_evidence_write(text,text,text,bytea) TO ingestion_worker')
            assert boot.execute("SELECT proacl::text FROM pg_proc WHERE oid='public.ingestion_intake_evidence_write(text,text,text,bytea)'::regprocedure").fetchone()==acl
        with support.actor() as c:closed=op.close(c,state[-1],lambda v:state.append(copy.deepcopy(v)))
        assert closed['runtime_access']=='DISABLED' and closed['sessions']=='ABSENT' and closed['temporary_owner']=='REMOVED'
        assert closed['password_verifiers']==('RETAINED' if mode in ('stable','interface_mismatch') else 'CLEARED')
        with support.actor() as c:op.dormant(c,stable_verifiers=value['verifier_sha256'] if mode in ('stable','interface_mismatch') else None)
