"""Focused disposable PG17 validation of NEW owner phases only.

Existing installation fixture is reused as SETUP, never its unchanged suite.
All bootstrap grants/passwords/session privileges below are synthetic fixture
conditions, not assertions about current production permissions.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

import psycopg
import pytest
from psycopg import sql

from verification.ingestion_storage import intake_owner as op

FIXTURE=Path('docs/design/b-owner-finite-20261031/disposable-fixture/fixture_support.py')
spec=importlib.util.spec_from_file_location('finite_fixture_support',FIXTURE)
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
world=support.world


@pytest.fixture
def installed(world):
    b=world['boot']
    for role,cap in op.ROLES.items():
        b.execute(sql.SQL('ALTER ROLE {} NOLOGIN PASSWORD NULL;ALTER ROLE {} RESET ALL').format(sql.Identifier(role),sql.Identifier(role)))
        rows=b.execute('SELECT grantor::regrole::text FROM pg_auth_members WHERE roleid=%s::regrole AND member=%s::regrole',(cap,role)).fetchall()
        for row in rows:
            b.execute(sql.SQL('REVOKE {} FROM {} GRANTED BY {} CASCADE').format(sql.Identifier(cap),sql.Identifier(role),sql.Identifier(row[0])))
    support.seeded.__wrapped__(world)
    # Synthetic pre-existing ADMIN-only rights needed by PG17 ALTER ROLE and
    # the already-supported member grant/revoke primitives. Production must
    # prove these rights; the implementation never grants them to itself.
    for name in [*op.ROLES,*op.ROLES.values()]:
        b.execute(sql.SQL('GRANT {} TO postgres WITH ADMIN TRUE,INHERIT FALSE,SET FALSE').format(sql.Identifier(name)))
    with support.actor() as c:support.execute(c)
    assert world['server_version']//10000==17
    return world


def binding():
    return dict(version='FINITE_INTAKE_OWNER_V1',period='finite-B-fixture',route='POOLER',
                hostaddr='192.0.2.1',owner_hostaddr='192.0.2.2',valid_until=time.time()+1800,
                execution_binding=copy.deepcopy(op.APPLICATION_BINDING),
                accepted_stop=copy.deepcopy(op.ACCEPTED_STOP))


def accepted(world):
    c=world['boot'];ctl=op.control(c);ctl.update(global_stop=None,manual_stop=None)
    c.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL))


def save_to(box):
    def save(v):box[:]=[json.loads(json.dumps(v))]
    return save


def open_access(world):
    accepted(world);box=[]
    with support.actor() as c:r=op.activate(c,binding(),save_to(box))
    assert r['outcome']=='COMMIT_ACKNOWLEDGED'
    return box


def test_exact_stop_disposition_preserves_history_generation_and_privileges(installed,record_property):
    b=installed['boot'];before=op.control(b);members=b.execute(op.MEMBERS).fetchall()
    with support.actor() as c:
        assert c.execute('SELECT rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()==(False,)
        result=op.stop_disposition(c,op.DECISIONS);op.owner_absent(c)
    expected=copy.deepcopy(before);expected.update(global_stop=None,manual_stop=None)
    assert op.control(b)==expected and b.execute(op.MEMBERS).fetchall()==members
    assert result['historical_controller_closure']=='UNKNOWN' and result['stop']['hard_stop_generation']==5
    record_property('postgres_version',installed['server_version']);record_property('actor_superuser',False)


@pytest.mark.parametrize('drift',['generation','oldham','oldham_expiry_type','oldham_counter_type','recovery','unfinished','intent','active_grant','function'])
def test_disposition_refuses_drift_atomically(installed,drift):
    b=installed['boot'];ctl=op.control(b)
    if drift=='generation':ctl['hard_stop_generation']=6
    elif drift=='oldham':ctl['oldham_allowances'][op.OLDHAM]['revoked']=False
    elif drift=='oldham_expiry_type':ctl['grants'][op.OLDHAM]['expires_at']=False
    elif drift=='oldham_counter_type':ctl['grants'][op.OLDHAM]['source_calls']=False
    elif drift=='recovery':b.execute("UPDATE ingestion_work_items SET fence=3 WHERE key=%s",(op.RECOVERED[0],))
    elif drift=='unfinished':ctl['intake_run']=dict(state='OPEN')
    elif drift=='intent':b.execute("UPDATE ingestion_work_items SET phase='SOURCE_INTENT' WHERE key=%s",(op.RECOVERED[0],))
    elif drift=='active_grant':ctl['grants']['SYNTHETIC_OTHER']=dict(expires_at=time.time()+100)
    else:b.execute('ALTER FUNCTION ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb) SECURITY INVOKER')
    b.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL))
    before=op.ledger_sha(b);members=b.execute(op.MEMBERS).fetchall()
    with support.actor() as c:
        with pytest.raises(op.Denied):op.stop_disposition(c,op.DECISIONS)
        op.owner_absent(c)
    assert op.ledger_sha(b)==before and b.execute(op.MEMBERS).fetchall()==members


def test_stop_requires_two_separate_owner_decisions(installed):
    with support.actor() as c:
        with pytest.raises(op.Denied,match='BOTH_EXPLICIT'):op.stop_disposition(c,op.DECISIONS[:1])


def test_activation_and_independent_closure_exact_roundtrip(installed):
    b=installed['boot'];accepted(installed)
    b.execute("ALTER ROLE ingestion_worker_login SET application_name TO 'retained-fixture-setting'")
    before_ledger=op.ledger_sha(b);before_members=b.execute(op.MEMBERS).fetchall();prior=op.settings(b)
    box=[]
    with support.actor() as c:result=op.activate(c,binding(),save_to(box))
    assert result['valid_until']<time.time()+2100
    assert len(b.execute(op.MEMBERS).fetchall())==len(before_members)+2
    for role in op.ROLES:
        with psycopg.connect(host='127.0.0.1',port=5432,dbname='postgres',user=role,password=box[0]['passwords'][role]) as runtime:
            assert runtime.execute('SELECT current_user').fetchone()==(role,)
    with support.actor() as c:result=op.close(c,box[0],save_to(box))
    assert result['runtime_access']=='DISABLED' and result['sessions']=='ABSENT'
    assert op.ledger_sha(b)==before_ledger and b.execute(op.MEMBERS).fetchall()==before_members and op.settings(b)==prior
    assert box[0]['passwords']=={}


@pytest.mark.parametrize('seconds',[30,960,2101,7*86400])
def test_short_validity_bounds_refuse_without_effect(installed,seconds):
    accepted(installed);b=binding();b['valid_until']=time.time()+seconds;box=[]
    with support.actor() as c:
        with pytest.raises(op.Denied,match='VALIDITY'):op.activate(c,b,save_to(box))
    assert box==[]


def test_missing_original_admin_right_is_not_repaired(installed):
    accepted(installed);b=installed['boot'];b.execute('REVOKE ingestion_worker_login FROM postgres CASCADE')
    before=b.execute(op.MEMBERS).fetchall()
    with support.actor() as c:
        with pytest.raises(op.Denied,match='EXISTING_RUNTIME_ADMIN'):op.activate(c,binding(),lambda _:None)
    assert b.execute(op.MEMBERS).fetchall()==before


def test_vault_failure_before_effect_rolls_back(installed):
    accepted(installed);b=installed['boot'];prior=op.settings(b);members=b.execute(op.MEMBERS).fetchall()
    def fail(_):raise OSError('synthetic vault unavailable')
    with support.actor() as c:
        with pytest.raises(OSError):op.activate(c,binding(),fail)
    assert b.execute(op.MEMBERS).fetchall()==members and op.settings(b)==prior
    assert all(not r[1] and r[2] for r in b.execute(op.ROLE_QUERY,(list(op.ROLES),)))


def test_lost_local_postcommit_save_has_independent_failure_closure(installed):
    accepted(installed);box=[];count=0
    def fail_after_commit(v):
        nonlocal count
        count+=1
        if count==2:raise OSError('synthetic lost local acknowledgement')
        save_to(box)(v)
    with support.actor() as c:
        with pytest.raises(OSError):op.activate(c,binding(),fail_after_commit)
    assert box[0]['state']=='ARMED_BEFORE_ACTIVATION'
    b=installed['boot'];ctl=op.control(b);ctl.update(manual_stop='NEW_FAILURE_STOP',last_hard_stop='NEW_FAILURE_STOP',hard_stop_generation=6)
    b.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL))
    with support.actor() as c:result=op.close(c,box[0],save_to(box))
    assert result['stop_preserved']['hard_stop_generation']==6 and op.control(b)==ctl


def test_lost_commit_reply_requires_independent_closure_not_activation_retry(installed):
    accepted(installed);box=[]
    class LostReply:
        def __init__(self,c):self.c=c;self.once=True
        def __getattr__(self,k):return getattr(self.c,k)
        def execute(self,q,params=None):
            result=self.c.execute(q,params)
            if q=='COMMIT' and self.once:
                self.once=False;raise psycopg.OperationalError('synthetic lost COMMIT reply after commit')
            return result
    with support.actor() as c:
        with pytest.raises(psycopg.OperationalError):op.activate(LostReply(c),binding(),save_to(box))
    assert box[0]['state']=='ARMED_BEFORE_ACTIVATION'
    with support.actor() as c:r=op.close(c,box[0],save_to(box))
    assert r['runtime_access']=='DISABLED'


def test_sql_failure_mid_activation_rolls_back_both_logins_memberships_and_timeouts(installed):
    accepted(installed);b=installed['boot'];before=op.settings(b);members=b.execute(op.MEMBERS).fetchall();box=[]
    class SQLFailure:
        def __init__(self,c):self.c=c
        def __getattr__(self,k):return getattr(self.c,k)
        def execute(self,q,params=None):
            rendered=q.as_string(self.c) if isinstance(q,sql.Composable) else q
            if 'ALTER ROLE "ingestion_effect_login" LOGIN PASSWORD' in rendered:
                return self.c.execute('SELECT 1/0')
            return self.c.execute(q,params)
    with support.actor() as c:
        with pytest.raises(psycopg.errors.DivisionByZero):op.activate(SQLFailure(c),binding(),save_to(box))
        op.owner_absent(c)
    assert op.settings(b)==before and b.execute(op.MEMBERS).fetchall()==members
    assert all(not row[1] and row[2] for row in b.execute(op.ROLE_QUERY,(list(op.ROLES),)))


def test_existing_signal_rights_resolve_exact_surviving_session_without_new_grants(installed):
    b=installed['boot'];b.execute('GRANT pg_signal_backend TO postgres');box=open_access(installed)
    runtime=psycopg.connect(host='127.0.0.1',port=5432,dbname='postgres',user='ingestion_worker_login',password=box[0]['passwords']['ingestion_worker_login'])
    try:
        with support.actor() as c:r=op.close(c,box[0],save_to(box))
        assert r['sessions']=='ABSENT' and b.execute("SELECT count(*) FROM pg_stat_activity WHERE usename='ingestion_worker_login'").fetchone()[0]==0
    finally:runtime.close();b.execute('REVOKE pg_signal_backend FROM postgres')


def test_closure_binds_actual_supported_registrar_marker_without_inventing_marker_fields(installed):
    from datetime import datetime,timedelta,timezone,date
    from app.ingestion.daily_intake import current_windows
    from app.ingestion.idox_adapter import IdoxListingContract
    from app.ingestion.ledger import DEFAULT_LIMITS,digest
    from app.ingestion.listing_screening import ScreeningRule,RULE_V3
    from verification.discovery.idox_window import WindowConfig
    from verification.ingestion_storage.operational_owner import Owner
    from verification.ingestion_storage.chain_registration import capture_registration
    from verification.ingestion_storage.daily_intake_runtime import registration_payload
    from verification.ingestion_storage.scope_binding import binding_for
    b=installed['boot'];b.execute('GRANT ingestion_barrier_releaser TO postgres WITH ADMIN TRUE,INHERIT FALSE,SET FALSE')
    box=open_access(installed);bv=box[0]['binding']
    owner=Owner(support.actor,lambda *_:None,lambda:None,expiry=datetime.now(timezone.utc)+timedelta(seconds=1200),bindings=op.APPLICATION_BINDING)
    policy=dict(hostaddr=None,route='DISPOSABLE',expires_at=time.time()+1700,max_runs=1,overlap_days=7,
        expected_stop=op.ACCEPTED_STOP,execution_binding=op.APPLICATION_BINDING,test_evidence=True,
        screening_config=digest(ScreeningRule(RULE_V3,unit_threshold=10,link_related=False).config()),
        councils={c:dict(contract='synthetic-current-'+c,qualification_sha256='9'*64) for c in ('tameside','manchester')})
    owner.register_intake_period(bv['period'],policy)
    row=current_windows(datetime.now(timezone.utc),['tameside'])[0]
    contract=IdoxListingContract('synthetic-current-tameside',WindowConfig('tameside','RECEIVED',
        date.fromisoformat(row['start']),date.fromisoformat(row['end']),0,60),'9'*64)
    reg=capture_registration(owner,binding_for('tameside'),contract,row['start'],row['end'],
        revision='synthetic-current-capture',item_limits=DEFAULT_LIMITS)
    payload=registration_payload(bv['period'],reg,op.APPLICATION_BINDING,run_id='a'*32)
    with psycopg.connect(host='127.0.0.1',port=5432,dbname='postgres',user='ingestion_worker_login',password=box[0]['passwords']['ingestion_worker_login'],autocommit=True) as runtime:
        runtime.execute('SELECT public.ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(payload),))
    marker=op.control(b)['intake_run']
    assert marker['state']=='OPEN' and 'execution_binding' not in marker
    with support.actor() as c:r=op.close(c,box[0],save_to(box))
    assert reg.authority in r['authorities'] and r['open_run_requires_reconciliation'] is True
    assert op.control(b)['intake_run']==marker and op.control(b)['grants'][reg.authority]['expires_at']==0


def test_changed_inventory_cannot_prevent_initial_access_disablement(installed):
    box=open_access(installed);b=installed['boot']
    b.execute('ALTER FUNCTION ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb) SECURITY INVOKER')
    with support.actor() as c:
        with pytest.raises(op.Denied,match='INVENTORY'):op.close(c,box[0],save_to(box))
    assert all(not r[1] and r[2] for r in b.execute(op.ROLE_QUERY,(list(op.ROLES),)))
    assert box[0]['state']=='ACCESS_DISABLED_ACKNOWLEDGED'


@pytest.mark.parametrize('lost',['monitoring','capability_admin'])
def test_lost_later_cleanup_permission_cannot_prevent_no_login_containment(installed,lost):
    box=open_access(installed);b=installed['boot']
    name='pg_read_all_stats' if lost=='monitoring' else 'ingestion_worker'
    # Synthetic concurrent permission loss, deliberately outside the promised
    # production no-concurrency condition; no automatic privilege repair.
    b.execute(sql.SQL('REVOKE {} FROM postgres CASCADE').format(sql.Identifier(name)))
    try:
        with support.actor() as c:
            with pytest.raises(op.Denied):op.close(c,box[0],save_to(box))
        assert all(not row[1] and row[2] for row in b.execute(op.ROLE_QUERY,(list(op.ROLES),)))
        assert box[0]['state']=='ACCESS_DISABLED_ACKNOWLEDGED'
    finally:
        if lost=='monitoring':b.execute('GRANT pg_read_all_stats TO postgres')


def test_surviving_session_without_existing_signal_right_is_not_claimed_closed(installed):
    box=open_access(installed)
    runtime=psycopg.connect(host='127.0.0.1',port=5432,dbname='postgres',user='ingestion_worker_login',password=box[0]['passwords']['ingestion_worker_login'])
    try:
        with support.actor() as c:
            with pytest.raises(op.Denied,match='SESSIONS_UNRESOLVED'):op.close(c,box[0],save_to(box))
        assert box[0]['state']=='ACCESS_DISABLED_ACKNOWLEDGED'
    finally:runtime.close()


def projected_idox_capture():
    """Actual supported nonempty reader/adapter over synthetic transport only."""
    from datetime import date
    from tests.e2e_connection_support import idox_audit,entry,SCHEME,outer
    from verification.discovery.idox_window import WindowConfig
    from app.ingestion.idox_adapter import IdoxListingContract
    from app.ingestion.ledger import DEFAULT_LIMITS
    c=WindowConfig('tameside','RECEIVED',date(2026,10,24),date(2026,10,30),0,60)
    source=idox_audit('tameside',[entry('READBACK_SYNTHETIC/26',SCHEME)],c.start,c.end)
    receipt=IdoxListingContract('synthetic-current-tameside',c,'9'*64).project(source,outer(),DEFAULT_LIMITS)
    receipt.pop('window')  # existing Coordinator.retained_capture retention step
    return receipt


def terminal_fixture(world):
    accepted(world)  # modeled post-disposition B state; initial fixture stays post-cleanup/stopped
    b=world['boot'];binding_value=binding();run_id='a'*32
    pub=dict(commit='b'*40,sha256='c'*64,readback_verified=True,
             path=f'docs/design/ingestion-operational-execution-daily-intake/{binding_value["period"]}/{run_id}/final/result-before-publication.json')
    ctl=op.control(b);roots={'tameside':'d'*64,'manchester':'e'*64};day='2026-10-30'
    ctl['intake_run']=dict(id=run_id,period=binding_value['period'],
                           state='VERIFIED',status='RETAINED_AND_SCREENED',publication=pub,day=day)
    ctl['intake_periods']={binding_value['period']:dict(days={day:roots},execution_binding=binding_value['execution_binding'])}
    for council,key in roots.items():
        authority='SYNTHETIC_B_AUTHORITY' if council=='tameside' else 'SYNTHETIC_B_AUTHORITY_MANCHESTER'
        ctl['grants'][authority]=dict(expires_at=0,intake_run=run_id,intake_period=binding_value['period'],
            capture_key=key,execution_binding=binding_value['execution_binding'])
    b.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL))
    for council,key in roots.items():
        # Actual projected nonempty Idox shape plus Manchester explicit zero.
        # Counter rows and remote archive references are synthetic fixture data.
        checkpoint=projected_idox_capture() if council=='tameside' else dict(kind='LISTING_RECEIPT_V1',council=council,records=[],explicit_zero=True,source_sha256='1'*64)
        checkpoint['durable_archive']=dict(commit='f'*40,path=f'docs/design/ingestion-operational-execution-daily-intake/{binding_value["period"]}/{run_id}/capture-{1 if council=="tameside" else 2}/source.json',sha256=checkpoint['source_sha256'],readback_verified=True)
        patch=dict(key=key,state='COMPLETE',task='DISCOVERY',checkpoint=checkpoint,subject=dict(council=council))
        b.execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(t)||%s::jsonb)).* FROM ingestion_work_items t WHERE key=%s",(json.dumps(patch),op.CONTROL))
        if council=='tameside':
            for task,child_key,checkpoint in [('SCREENING','7'*64,dict(evidence_label='SYNTHETIC_COUNTER_ONLY')),
                    ('LISTING_METADATA','8'*64,dict(plan=dict(capture_key=key),evidence_label='SYNTHETIC_COUNTER_ONLY'))]:
                child=dict(key=child_key,state='COMPLETE',task=task,checkpoint=checkpoint,dependencies=[key])
                b.execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(t)||%s::jsonb)).* FROM ingestion_work_items t WHERE key=%s",(json.dumps(child),key))
    return binding_value,dict(run_id=run_id,publication=pub)


def test_independent_terminal_projection_reads_both_councils_and_exact_publication(installed,record_property):
    b=installed['boot'];binding_value,expected=terminal_fixture(installed);before=op.ledger_sha(b);members=b.execute(op.MEMBERS).fetchall()
    with support.actor() as c:
        assert c.execute('SELECT rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()==(False,)
        r=op.finalisation(c,binding_value,expected)
    assert {v['council'] for v in r['captures']}=={'tameside','manchester'} and r['publication']==expected['publication']
    assert op.ledger_sha(b)==before and b.execute(op.MEMBERS).fetchall()==members
    record_property('postgres_version',installed['server_version']);record_property('actor_superuser',False)


def test_actual_supported_idox_retention_has_records_and_no_invented_zero_flag():
    receipt=projected_idox_capture()
    assert 'explicit_zero' not in receipt and 'window' not in receipt
    assert len(receipt['records'])==1 and receipt['segments'][0]['terminal']=='EXPLICIT_LAST_EQUALS_TOTAL'


@pytest.mark.parametrize('drift',['run','publication','open','incomplete','expiry','boolean_expiry','council','zero','archive','screen'])
def test_independent_readback_refuses_false_terminal_success(installed,drift):
    b=installed['boot'];bv,e=terminal_fixture(installed);ctl=op.control(b)
    if drift=='run':e['run_id']='9'*32
    elif drift=='publication':e['publication']=dict(e['publication'],sha256='9'*64)
    elif drift=='open':ctl['intake_run']['state']='OPEN'
    elif drift=='incomplete':ctl['intake_run']['status']='INCOMPLETE'
    elif drift=='expiry':ctl['grants']['SYNTHETIC_B_AUTHORITY']['expires_at']=time.time()-1
    elif drift=='boolean_expiry':ctl['grants']['SYNTHETIC_B_AUTHORITY']['expires_at']=False
    elif drift=='council':del ctl['intake_periods'][bv['period']]['days']['2026-10-30']['manchester']
    else:
        cp=b.execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s',('d'*64,)).fetchone()[0]
        if drift=='zero':cp['records']=[];cp['explicit_zero']=True  # unsupported Tameside zero must refuse
        elif drift=='archive':cp['durable_archive']=None
        else:b.execute("UPDATE ingestion_work_items SET state='QUEUED' WHERE key=%s",('7'*64,))
        b.execute('UPDATE ingestion_work_items SET checkpoint=%s::json WHERE key=%s',(json.dumps(cp),'d'*64))
    b.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL))
    before=op.ledger_sha(b)
    with support.actor() as c:
        with pytest.raises(op.Denied):op.finalisation(c,bv,e)
    assert op.ledger_sha(b)==before
