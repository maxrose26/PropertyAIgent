"""Policy v3 (generation-2 form probe) on a REAL disposable PostgreSQL 17 with the real installed ledger and the reviewed 18 October successor policy applied first. Verifies: exact recognition of the
observed stop state for the single named allowance only; every other state and name refused; the existing generation 0/1 behaviour preserved; nothing else in the database changed. Loopback only."""
import hashlib
import json
import os
import secrets
import time
from datetime import datetime,timedelta,timezone
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from app.ingestion.ledger import digest,DEFAULT_LIMITS
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage.operational_owner import Owner,item
from tests.test_discovery_ingestion_provisioning_pg import ROLES as BASE_ROLES,PACKAGE

ROLE='policy_migrator'
EXTRA=['ingestion_effect_login','ingestion_effect_broker','ingestion_recovery_operator']
V1=Path('docs/design/ingestion-operational-required-20261018/successor-policy.sql')
V3=Path('docs/design/ingestion-form-probe-20261021/policy-generation2.sql')
NAMED='AUTHORISE_INGESTION_BOLTON_FORM_PROBE_ONCE_20261021_PROBE'
IDOX='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE'
STOP2_SHA='675b69adfe844e2e443bcdaaf26b5d745f03b01a6651b025ad2a002445f06b21'
STOP1_SHA='a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e'
SUBJECT=dict(kind='DISCOVERY_SCOPE',council='bolton',start='2026-10-16',end='2026-10-16',semantics='RECEIVED')
BINDING=dict(revision='a'*40,workflow_sha256='b'*64,manifest_sha256='c'*64)


@pytest.fixture
def ledger():
    raw=os.environ.get('INGESTION_PROVISIONING_TEST_URL')
    if not raw:pytest.skip('fixed disposable PG17 required')
    info=psycopg.conninfo.conninfo_to_dict(raw)
    assert (info['host'],info['port'],info['dbname'],info['user'])==('127.0.0.1','5432','ingestion_provisioning_test','provisioning_bootstrap')
    password=secrets.token_urlsafe(48)
    def connector():return psycopg.connect(**{**info,'user':ROLE,'password':password},autocommit=True,prepare_threshold=None,connect_timeout=3)
    with psycopg.connect(raw,autocommit=True) as boot:
        boot.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER CREATEROLE CREATEDB BYPASSRLS NOINHERIT PASSWORD {}').format(sql.Identifier(ROLE),sql.Literal(password)))
        boot.execute(sql.SQL('GRANT USAGE,CREATE ON SCHEMA public TO {} WITH GRANT OPTION').format(sql.Identifier(ROLE)))
        boot.execute(sql.SQL('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO {} WITH GRANT OPTION').format(sql.Identifier(ROLE)))
        boot.execute(sql.SQL('GRANT SELECT(rolname,rolpassword) ON pg_catalog.pg_authid TO {}').format(sql.Identifier(ROLE)))
        boot.execute(sql.SQL('GRANT pg_read_all_stats TO {} WITH INHERIT TRUE').format(sql.Identifier(ROLE)))
        boot.execute('CREATE SCHEMA extensions')
        boot.execute("CREATE EXTENSION pg_stat_statements WITH SCHEMA extensions VERSION '1.11'")
        boot.execute(sql.SQL('GRANT USAGE ON SCHEMA extensions TO {}').format(sql.Identifier(ROLE)))
        try:
            with connector() as c:
                c.execute((PACKAGE/'install.sql').read_text())
                c.execute('REVOKE ingestion_worker FROM ingestion_worker_login')
                c.execute('REVOKE ingestion_storage_operator FROM ingestion_storage_login')
            boot.execute("SELECT public.ingestion_raise_stop('STORAGE_TEST_STOP')")
            installer=Owner(connector,lambda *_:None,lambda:None,identity=ROLE,expiry=datetime.now(timezone.utc)+timedelta(minutes=30),bindings={})
            installer.install()
            def control():return boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            def set_control(ctl):boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
            ctl=control();ctl['hard_stop_generation']=1;ctl['last_hard_stop']='OPERATIONAL_FIRST_CONNECTION_FAILURE_CLEANUP_20261018';set_control(ctl)
            installer.reuse_installed=True
            with installer.connection() as c_:installer.script(c_,V1)      # the reviewed 18 October successor policy, exactly as in production
            yield boot,connector,installer,control,set_control
        finally:
            boot.execute('DROP TABLE IF EXISTS public.ingestion_work_attempts,public.ingestion_work_items CASCADE')
            boot.execute('DROP EXTENSION IF EXISTS pg_stat_statements')
            boot.execute('DROP SCHEMA IF EXISTS extensions')
            for r in [*EXTRA,*BASE_ROLES,ROLE]:
                if boot.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(r,)).fetchone():boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(r)))
            for r in [*EXTRA,*BASE_ROLES,ROLE]:boot.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(r)))


def observed_state(set_control,control,*,extra_exceptions=2):
    """The observed generation-2 control record: stops as observed, two revoked historical grants and exceptions (so the cap leaves exactly one slot)."""
    ctl=control()
    ctl['manual_stop']=IDOX;ctl['last_hard_stop']=IDOX;ctl['hard_stop_generation']=2
    ctl['grants']={};ctl['bolton_exceptions']={}
    for i in range(extra_exceptions):
        name='HISTORICAL_%d'%i
        ctl['grants'][name]=dict(keys=['k'],expires_at=0,source_calls=0,writes=0,login='ingestion_worker_login',bindings={'k':{}})
        ctl['bolton_exceptions'][name]=dict(authority=name,transport='REQUESTS_IDOX',grant_binding={},expires_at=0,hard_stop_generation=1)
    set_control(ctl);return ctl


def probe_grant(boot,control,set_control,*,name=NAMED,expires=None,revision='9'*64):
    identity=dict(subject=SUBJECT,task='DISCOVERY',contract=orr.CONTRACT,revision=revision)
    root=item(identity,max_attempts=1,limits=dict(DEFAULT_LIMITS,requests=1,bytes=262144,rows=0,pages=1))
    boot.execute('INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,%s::json)',(json.dumps(root),))
    bindings={root['key']:{k:root[k] for k in ('subject','task','contract','revision')}}
    grant=dict(keys=sorted(bindings),contracts=[orr.CONTRACT],expires_at=expires or time.time()+600,source_calls=1,writes=0,login='ingestion_worker_login',effect_login='ingestion_effect_login',workers=['required_once'],
               bindings=bindings,detail_source_keys=[],capture_key=root['key'],capture_only=False,execution_binding=dict(BINDING),completion_outcomes={'DISCOVERY':['ENUMERATED_METADATA_RETAINED']})
    ctl=control();ctl['grants'][name]=grant;set_control(ctl)
    return grant


def payload(grant,*,name=NAMED,generation=2,sha=STOP2_SHA):
    return dict(authority=name,transport='REQUESTS_IDOX',grant_binding={k:v for k,v in grant.items() if k not in ('source_calls','writes')},stop_checkpoint_sha256=sha,hard_stop_generation=generation,**BINDING)


def register(boot,p):
    return boot.execute('SELECT public.ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(p),)).fetchone()[0]


def allowed(boot,ctl,authority,subject=None):
    return boot.execute('SELECT public.ingestion_bolton_allowed(%s::jsonb,%s,%s::jsonb)',(json.dumps(ctl),authority,json.dumps(subject or {'council':'bolton'})) ).fetchone()[0]


def apply_v3(installer):
    with installer.connection() as c:installer.script(c,V3)


def function_fingerprints(boot):
    rows=boot.execute("SELECT p.proname,md5(pg_get_functiondef(p.oid)),p.proowner::regrole::text,coalesce(p.proacl::text,'') FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' ORDER BY 1,2").fetchall()
    return {r[0]:tuple(r[1:]) for r in rows}


def memberships(boot):
    return [tuple(map(str,r)) for r in boot.execute("SELECT member::regrole::text,roleid::regrole::text,admin_option,inherit_option,set_option,grantor::regrole::text FROM pg_auth_members ORDER BY 1,2,6").fetchall()]


# ------------------------------------------------------------------------------------------------ before v3: the installed policy refuses the observed state
def test_the_installed_policy_refuses_the_observed_state_before_v3(ledger):
    boot,connector,installer,control,set_control=ledger
    observed_state(set_control,control);grant=probe_grant(boot,control,set_control)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant))
    ctl=control();ctl['bolton_exceptions'][NAMED]=payload(grant)|dict(expires_at=grant['expires_at'])
    assert allowed(boot,ctl,NAMED) is False


# ------------------------------------------------------------------------------------------------ v3
def test_v3_registers_only_the_named_allowance_in_the_exact_observed_state(ledger):
    boot,connector,installer,control,set_control=ledger
    observed_state(set_control,control);grant=probe_grant(boot,control,set_control)
    apply_v3(installer)
    exception=register(boot,payload(grant))      # the named allowance, exact state, exact digest
    assert exception['authority']==NAMED and exception['hard_stop_generation']==2
    ctl=control();assert NAMED in ctl['bolton_exceptions'] and len(ctl['bolton_exceptions'])==3 and ctl['hard_stop_generation']==2 and ctl['manual_stop']==IDOX      # third and last slot; generation untouched
    assert allowed(boot,ctl,NAMED) is True


@pytest.mark.parametrize('mutation',['other_name','wrong_digest','payload_generation_1','payload_generation_3','control_generation_3','other_manual_stop','other_last_hard_stop','global_stop_changed','cap_reached','already_registered'])
def test_v3_refuses_every_other_name_and_state(ledger,mutation):
    boot,connector,installer,control,set_control=ledger
    observed_state(set_control,control,extra_exceptions=3 if mutation=='cap_reached' else 2)
    name=NAMED+'_OTHER' if mutation=='other_name' else NAMED
    grant=probe_grant(boot,control,set_control,name=name)
    apply_v3(installer)
    p=payload(grant,name=name)
    if mutation=='wrong_digest':p=payload(grant,sha=STOP1_SHA)
    if mutation=='payload_generation_1':p=payload(grant,generation=1)
    if mutation=='payload_generation_3':p=payload(grant,generation=3)
    ctl=control()
    if mutation=='control_generation_3':ctl['hard_stop_generation']=3
    if mutation=='other_manual_stop':ctl['manual_stop']='SOMETHING_ELSE'
    if mutation=='other_last_hard_stop':ctl['last_hard_stop']='SOMETHING_ELSE'
    if mutation=='global_stop_changed':ctl['global_stop']={'reason':'OTHER','run':'1'}
    if mutation=='already_registered':ctl['bolton_exceptions'][NAMED]=dict(authority=NAMED,transport='REQUESTS_IDOX',grant_binding={},expires_at=0,hard_stop_generation=2)
    set_control(ctl)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,p)


def test_v3_honours_the_exception_only_in_the_exact_state_for_the_named_allowance(ledger):
    boot,connector,installer,control,set_control=ledger
    observed_state(set_control,control);grant=probe_grant(boot,control,set_control)
    apply_v3(installer);register(boot,payload(grant))
    good=control();assert allowed(boot,good,NAMED) is True
    for name,change in (('generation 3',dict(hard_stop_generation=3)),('other manual stop',dict(manual_stop='X')),('other last hard stop',dict(last_hard_stop='X')),('global stop changed',dict(global_stop={'reason':'OTHER','run':'1'}))):
        assert allowed(boot,dict(good,**change),NAMED) is False,name
    other=json.loads(json.dumps(good));other['grants']['OTHER']=other['grants'][NAMED];other['bolton_exceptions']['OTHER']=dict(other['bolton_exceptions'][NAMED],authority='OTHER')
    assert allowed(boot,other,'OTHER') is False      # same state, same shape, but not the named allowance
    expired=json.loads(json.dumps(good));expired['bolton_exceptions'][NAMED]['expires_at']=time.time()-1
    assert allowed(boot,expired,NAMED) is False
    mismatched=json.loads(json.dumps(good));mismatched['grants'][NAMED]['keys']=['tampered']
    assert allowed(boot,mismatched,NAMED) is False
    assert allowed(boot,good,NAMED,{'council':'salford'}) is False
    wrong_transport=json.loads(json.dumps(good));wrong_transport['bolton_exceptions'][NAMED]['transport']='BROWSER'
    assert allowed(boot,wrong_transport,NAMED) is False


def test_v3_preserves_the_existing_generation_0_and_1_behaviour(ledger):
    boot,connector,installer,control,set_control=ledger
    apply_v3(installer)      # state is the accepted generation-1 baseline: STORAGE_TEST_STOP, the pinned 18 October last_hard_stop
    assert control()['hard_stop_generation']==1 and control()['manual_stop']=='STORAGE_TEST_STOP'
    grant=probe_grant(boot,control,set_control,name='ANY_OTHER_AUTHORITY_GEN1',revision='8'*64)
    exception=register(boot,payload(grant,name='ANY_OTHER_AUTHORITY_GEN1',generation=1,sha=STOP1_SHA))
    assert exception['hard_stop_generation']==1      # behaves exactly as before for generation 1
    ctl=control();assert allowed(boot,ctl,'ANY_OTHER_AUTHORITY_GEN1') is True
    observed_state(set_control,control)      # now the observed state: a generation-1 style registration for another name is refused
    grant2=probe_grant(boot,control,set_control,name='ANY_OTHER_AUTHORITY_GEN2',revision='7'*64)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant2,name='ANY_OTHER_AUTHORITY_GEN2',generation=1,sha=STOP1_SHA))
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant2,name='ANY_OTHER_AUTHORITY_GEN2',generation=2,sha=STOP2_SHA))


def test_installing_v3_changes_exactly_two_function_definitions_and_nothing_else(ledger):
    boot,connector,installer,control,set_control=ledger
    observed_state(set_control,control);probe_grant(boot,control,set_control)
    before=dict(functions=function_fingerprints(boot),control=digest(control()),memberships=memberships(boot),
                roles=[tuple(map(str,r)) for r in boot.execute("SELECT a.rolname,a.rolcanlogin,coalesce(a.rolpassword,''),coalesce(a.rolvaliduntil::text,''),coalesce(r.rolconfig::text,'') FROM pg_authid a JOIN pg_roles r ON r.oid=a.oid ORDER BY 1").fetchall()])
    apply_v3(installer)
    after=dict(functions=function_fingerprints(boot),control=digest(control()),memberships=memberships(boot),
               roles=[tuple(map(str,r)) for r in boot.execute("SELECT a.rolname,a.rolcanlogin,coalesce(a.rolpassword,''),coalesce(a.rolvaliduntil::text,''),coalesce(r.rolconfig::text,'') FROM pg_authid a JOIN pg_roles r ON r.oid=a.oid ORDER BY 1").fetchall()])
    changed=sorted(k for k in before['functions'] if before['functions'][k]!=after['functions'].get(k))
    assert changed==['ingestion_bolton_allowed','ingestion_register_bolton_exception'] and set(before['functions'])==set(after['functions'])      # exactly the two functions; no new function
    for k in changed:assert before['functions'][k][1:]==after['functions'][k][1:]      # owner and privileges of the two functions are unchanged
    assert before['control']==after['control']      # the control record (stops, grants, exceptions) is byte-for-byte unchanged
    assert before['memberships']==after['memberships'] and before['roles']==after['roles']      # no membership, option, password, validity or setting change; the temporary capability is gone
    apply_v3(installer)
    assert function_fingerprints(boot)==after['functions']      # idempotent


@pytest.mark.parametrize('absent',['manual_stop','last_hard_stop','hard_stop_generation'])
def test_v3_refuses_the_named_allowance_when_a_stop_field_is_absent_and_allows_nothing_v1_did_not(ledger,absent):
    boot,connector,installer,control,set_control=ledger
    observed_state(set_control,control);grant=probe_grant(boot,control,set_control)
    ctl=control();ctl.pop(absent);set_control(ctl)      # an absent field is NULL in SQL: it must be FALSE in the probe branch, never a widening
    ctl=control();ctl['bolton_exceptions'][NAMED]=payload(grant)|dict(expires_at=grant['expires_at']);ctl['grants'][NAMED]=grant
    under_v1=allowed(boot,ctl,NAMED)      # the installed (reviewed 18 October) policy, evaluated on the very same record
    apply_v3(installer)
    assert allowed(boot,ctl,NAMED)==under_v1      # v3 grants nothing that v1 did not (the original treats an absent manual stop as "no manual stop")
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant))      # and the registration is refused


def test_v3_does_not_honour_a_revoked_or_expired_probe_exception(ledger):
    boot,connector,installer,control,set_control=ledger
    observed_state(set_control,control);grant=probe_grant(boot,control,set_control)
    apply_v3(installer);register(boot,payload(grant))
    ctl=control();assert allowed(boot,ctl,NAMED) is True
    ctl['bolton_exceptions'][NAMED]['expires_at']=0
    assert allowed(boot,ctl,NAMED) is False      # revoked to zero (the invalidation): no longer honoured
    ctl=control();ctl['grants'][NAMED]['expires_at']=0
    assert allowed(boot,ctl,NAMED) is False      # the grant itself revoked: the binding no longer matches


def test_v3_still_pins_the_generation_1_last_hard_stop(ledger):
    boot,connector,installer,control,set_control=ledger
    apply_v3(installer)
    ctl=control();ctl['last_hard_stop']='SOMETHING_ELSE';set_control(ctl)      # generation 1 with a different last_hard_stop
    grant=probe_grant(boot,control,set_control,name='ANY_OTHER_AUTHORITY_GEN1',revision='6'*64)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant,name='ANY_OTHER_AUTHORITY_GEN1',generation=1,sha=STOP1_SHA))
