"""REQUIRES actual existing disposable PG17 service; no skipping or live fallback.
Synthetic bootstrap privileges below are fixture-only, never production facts.
"""
import copy
import hashlib
import time
import psycopg
import pytest
from tests.test_intake_owner_finite import installed,world,accepted,support
from tests.test_intake_owner_operations import inputs
from verification.ingestion_storage import intake_owner as op,intake_owner_operations as extra
from verification.ingestion_storage.operational_publication import canonical

@pytest.fixture
def period_world(installed):
    b=installed['boot'];accepted(installed)
    b.execute('GRANT ingestion_barrier_releaser TO postgres WITH ADMIN TRUE,INHERIT FALSE,SET FALSE GRANTED BY provisioning_bootstrap')
    return installed

def call(c,b,p,saved):
    state=dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=p)
    return extra.issue_period(c,b,p,state,lambda x:saved.append(copy.deepcopy(x)))

def test_pg17_success_exact_ledger_memberships_and_cleanup(period_world,tmp_path,record_property):
    boot=period_world['boot'];b,p=inputs(tmp_path);members=boot.execute(op.MEMBERS).fetchall();ctl=op.control(boot);before=op.ledger_sha(boot);saved=[]
    with support.actor() as c:
        assert c.execute('SELECT rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()==(False,)
        r=call(c,b,p,saved)
    entry=op.control(boot)['intake_periods'][b['period']]
    assert {k:entry[k] for k in p}==p and entry['days']=={} and r['connections']==1
    assert boot.execute(op.MEMBERS).fetchall()==members and op.ledger_sha(boot,ctl)==before
    assert saved[-1]['state']=='COMMIT_ACKNOWLEDGED'
    record_property('pg_version',period_world['server_version']);record_property('actor_superuser',False)

@pytest.mark.parametrize('drift',['policy','stop','inventory','capability','options'])
def test_pg17_preconditions_refuse_no_effect(period_world,tmp_path,drift):
    boot=period_world['boot'];b,p=inputs(tmp_path)
    if drift=='policy':p['max_runs']=2;b['period_policy_sha256']=hashlib.sha256(canonical(p)).hexdigest()
    if drift=='stop':
        ctl=op.control(boot);ctl['hard_stop_generation']=6
        boot.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(__import__('json').dumps(ctl),op.CONTROL))
    if drift=='inventory':boot.execute('ALTER FUNCTION ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb) SECURITY INVOKER')
    if drift=='capability':boot.execute('REVOKE ingestion_barrier_releaser FROM postgres CASCADE')
    if drift=='options':boot.execute('GRANT ingestion_barrier_releaser TO postgres WITH ADMIN TRUE,INHERIT TRUE,SET FALSE GRANTED BY provisioning_bootstrap')
    before=op.ledger_sha(boot);members=boot.execute(op.MEMBERS).fetchall()
    with support.actor() as c:
        with pytest.raises(Exception):call(c,b,p,[])
    assert op.ledger_sha(boot)==before and boot.execute(op.MEMBERS).fetchall()==members

class Fault:
    def __init__(self,c,mode):self.c=c;self.mode=mode
    def __getattr__(self,n):return getattr(self.c,n)
    def execute(self,s,params=None):
        if self.mode=='sql' and s=='SELECT public.ingestion_register_bolton_exception(%s::jsonb)':return self.c.execute('SELECT 1/0')
        result=self.c.execute(s,params)
        if self.mode=='temporary' and s=='GRANT ingestion_barrier_releaser TO CURRENT_USER WITH INHERIT TRUE, SET TRUE':self.c.execute('GRANT ingestion_barrier_releaser TO postgres WITH ADMIN TRUE,INHERIT TRUE,SET TRUE')
        if self.mode=='privilege' and s=='REVOKE ingestion_barrier_releaser FROM CURRENT_USER GRANTED BY CURRENT_USER':self.c.execute('GRANT ingestion_effect_login TO postgres WITH ADMIN FALSE,INHERIT FALSE,SET TRUE')
        if self.mode=='lost_commit' and s=='COMMIT':raise psycopg.OperationalError('synthetic lost acknowledgement after commit')
        return result

@pytest.mark.parametrize('fault',['sql','privilege','temporary','lost_commit'])
def test_pg17_atomic_rollback_and_lost_acknowledgement(period_world,tmp_path,fault):
    boot=period_world['boot'];b,p=inputs(tmp_path);before=op.ledger_sha(boot);members=boot.execute(op.MEMBERS).fetchall();saved=[]
    with support.actor() as c:
        with pytest.raises(Exception):call(Fault(c,fault),b,p,saved)
    assert boot.execute(op.MEMBERS).fetchall()==members
    if fault=='lost_commit':
        assert b['period'] in op.control(boot)['intake_periods'] and saved[-1]['state']=='COMMIT_INTENT_NO_RETRY'
    else:assert op.ledger_sha(boot)==before
