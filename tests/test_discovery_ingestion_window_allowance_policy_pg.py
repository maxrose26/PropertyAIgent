"""Policy v5 (generation-3 window demonstration) on a REAL disposable PostgreSQL 17 with the real installed ledger, the reviewed successor policy and then v3 and v4 exactly as in production. Verifies: the two named
allowances register in the exact generation-3 stop state, for the exact week scope only, with the cap exhausted by FOUR keys; nothing else is admitted; the cap holds for every other name and state; re-registration is
impossible; history is untouched; only two function definitions change. Loopback only."""
import json
import time

import psycopg
import pytest

from app.ingestion.ledger import digest,DEFAULT_LIMITS
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage.operational_owner import item
from tests.test_discovery_ingestion_policy_generation2_pg import (ledger,observed_state,probe_grant,payload,register,allowed,apply_v3,function_fingerprints,memberships,IDOX,STOP1_SHA,STOP2_SHA,NAMED as PROBE,BINDING,SUBJECT)
from tests.test_discovery_ingestion_capture_allowance_policy_pg import apply_v4,CAP as OLDCAP,SCR as OLDSCR

CAP=orr.WINDOW_AUTHORITY+'_CAPTURE'
SCR=orr.WINDOW_AUTHORITY+'_SCREEN'
V5=oo.GENERATION3_WINDOW_POLICY
G3=oo.GENERATION3_STOP['stop_state_sha256']
WEEK=dict(oo.WINDOW_SCOPE)


def apply_v5(installer):
    with installer.connection() as c:installer.script(c,V5)


def window_grant(boot,control,set_control,*,name=CAP,revision='9'*64,subject=None,calls=1):
    root=item(dict(subject=subject or WEEK,task='DISCOVERY',contract=orr.CONTRACT,revision=revision),max_attempts=1,limits=dict(DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6))
    boot.execute('INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,%s::json)',(json.dumps(root),))
    bindings={root['key']:{k:root[k] for k in ('subject','task','contract','revision')}}
    grant=dict(keys=sorted(bindings),contracts=[orr.CONTRACT],expires_at=time.time()+600,source_calls=calls,writes=0,login='ingestion_worker_login',effect_login='ingestion_effect_login',workers=['required_once'],bindings=bindings,
               detail_source_keys=[],capture_key=root['key'],capture_only=False,execution_binding=dict(BINDING),completion_outcomes={'DISCOVERY':['ENUMERATED_METADATA_RETAINED']})
    ctl=control();ctl['grants'][name]=grant;set_control(ctl)
    return grant


def generation3_exhausted(boot,connector,installer,control,set_control):
    """The state production is in now: v4 installed, generation 3 (manual stop and last hard stop IDOX), the cap exhausted by FOUR revoked keys: two historical, the probe and the 22 October capture."""
    observed_state(set_control,control);grant=probe_grant(boot,control,set_control)
    apply_v3(installer);register(boot,payload(grant))
    ctl=control();ctl['grants'][PROBE]['expires_at']=0;ctl['bolton_exceptions'][PROBE]['expires_at']=0;set_control(ctl)
    apply_v4(installer)
    g=probe_grant(boot,control,set_control,name=OLDCAP,revision='8'*64);register(boot,payload(g,name=OLDCAP))
    ctl=control();ctl['grants'][OLDCAP]['expires_at']=0;ctl['bolton_exceptions'][OLDCAP]['expires_at']=0
    ctl['hard_stop_generation']=3;set_control(ctl)      # the capture's fail-safe stop: generation 3, manual stop and last hard stop unchanged in value
    assert len(control()['bolton_exceptions'])==4 and oo.Owner.project_control(control(),time.time())['stop_state_sha256']==G3      # the derived digest equals the digest of this state
    return control()


def test_under_v4_the_generation_3_state_refuses_the_window_allowance(ledger):
    boot,connector,installer,control,set_control=ledger
    generation3_exhausted(boot,connector,installer,control,set_control)
    grant=window_grant(boot,control,set_control)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant,name=CAP,generation=3,sha=G3))      # v4: the problem being solved


def test_v5_registers_exactly_the_two_named_allowances_for_the_week_scope_with_the_cap_exhausted_and_touches_nothing_else(ledger):
    boot,connector,installer,control,set_control=ledger
    before=generation3_exhausted(boot,connector,installer,control,set_control)
    before_fn=function_fingerprints(boot);before_members=memberships(boot)
    apply_v5(installer)
    after_fn=function_fingerprints(boot)
    assert sorted(k for k in before_fn if before_fn[k]!=after_fn.get(k))==['ingestion_bolton_allowed','ingestion_register_bolton_exception'] and set(before_fn)==set(after_fn)
    assert memberships(boot)==before_members and control()==before      # the installation changes no record
    g_cap=window_grant(boot,control,set_control,name=CAP,revision='7'*64)
    e=register(boot,payload(g_cap,name=CAP,generation=3,sha=G3));assert e['authority']==CAP and e['hard_stop_generation']==3
    g_scr=window_grant(boot,control,set_control,name=SCR,revision='6'*64,calls=0)
    register(boot,payload(g_scr,name=SCR,generation=3,sha=G3))
    ctl=control()
    assert allowed(boot,ctl,CAP) is True and allowed(boot,ctl,SCR) is True and len(ctl['bolton_exceptions'])==6 and ctl['hard_stop_generation']==3 and ctl['manual_stop']==IDOX and ctl['last_hard_stop']==IDOX      # generation untouched
    for name in ('HISTORICAL_0','HISTORICAL_1',PROBE,OLDCAP):assert ctl['bolton_exceptions'][name]==before['bolton_exceptions'][name] and ctl['grants'][name]==before['grants'][name]
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(g_cap,name=CAP,generation=3,sha=G3))      # a name that exists can never be registered again


@pytest.mark.parametrize('name',[CAP,SCR])
def test_v5_requires_the_exact_week_scope_for_the_window_names(ledger,name):
    boot,connector,installer,control,set_control=ledger
    generation3_exhausted(boot,connector,installer,control,set_control);apply_v5(installer)
    other={**WEEK,'end':'2026-10-05'}
    for index,subject in enumerate((SUBJECT,other,{**WEEK,'council':'bury'},{**WEEK,'semantics':'VALIDATED'})):
        grant=window_grant(boot,control,set_control,name=name,revision=str(index+1)*64,subject=subject)
        with pytest.raises(psycopg.errors.Error):register(boot,payload(grant,name=name,generation=3,sha=G3))      # the day, a longer week, another council, another semantics: all refused
        ctl=control();ctl['grants'].pop(name);set_control(ctl)


def test_v5_does_not_admit_the_week_scope_to_any_other_name_and_keeps_the_day_scope_for_them(ledger):
    boot,connector,installer,control,set_control=ledger
    generation3_exhausted(boot,connector,installer,control,set_control);apply_v5(installer)
    grant=window_grant(boot,control,set_control,name='SOME_OTHER_ALLOWANCE',revision='5'*64)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant,name='SOME_OTHER_ALLOWANCE',generation=3,sha=G3))
    ctl=control();ctl['bolton_exceptions'].clear();ctl['bolton_exceptions']['HISTORICAL_0']=dict(authority='HISTORICAL_0',transport='REQUESTS_IDOX',grant_binding={},expires_at=0,hard_stop_generation=1);set_control(ctl)      # room under the cap
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant,name='SOME_OTHER_ALLOWANCE',generation=3,sha=G3))      # still refused by the stop predicate


@pytest.mark.parametrize('name',[CAP,SCR])
@pytest.mark.parametrize('state',['generation_2','generation_4','generation_1','other_manual_stop','other_last_hard_stop','absent_manual_stop','absent_generation','absent_last_hard_stop','wrong_digest','generation_2_digest'])
def test_v5_refuses_the_window_names_in_any_state_but_the_exact_generation_3_one(ledger,name,state):
    boot,connector,installer,control,set_control=ledger
    generation3_exhausted(boot,connector,installer,control,set_control);apply_v5(installer)
    ctl=control();sha=G3;generation=3
    if state=='generation_2':ctl['hard_stop_generation']=2;generation=2;sha=STOP2_SHA
    if state=='generation_4':ctl['hard_stop_generation']=4
    if state=='generation_1':ctl['hard_stop_generation']=1;generation=1;sha=STOP1_SHA
    if state=='other_manual_stop':ctl['manual_stop']='SOMETHING_ELSE'
    if state=='other_last_hard_stop':ctl['last_hard_stop']='SOMETHING_ELSE'
    if state=='absent_manual_stop':ctl.pop('manual_stop')
    if state=='absent_generation':ctl.pop('hard_stop_generation')
    if state=='absent_last_hard_stop':ctl.pop('last_hard_stop')
    if state=='wrong_digest':sha='0'*64
    if state=='generation_2_digest':sha=STOP2_SHA
    set_control(ctl)
    grant=window_grant(boot,control,set_control,name=name,revision='4'*64)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant,name=name,generation=generation,sha=sha))


@pytest.mark.parametrize('name',[CAP,SCR])
def test_v5_cap_exemption_needs_generation_3(ledger,name):
    boot,connector,installer,control,set_control=ledger
    generation3_exhausted(boot,connector,installer,control,set_control);apply_v5(installer)
    ctl=control();ctl['hard_stop_generation']=1;ctl['last_hard_stop']='OPERATIONAL_FIRST_CONNECTION_FAILURE_CLEANUP_20261018';ctl['manual_stop']='STORAGE_TEST_STOP';set_control(ctl)
    grant=window_grant(boot,control,set_control,name=name,revision='3'*64)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant,name=name,generation=1,sha=STOP1_SHA))
    ctl=control();ctl.pop('hard_stop_generation');set_control(ctl)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant,name=name,generation=1,sha=STOP1_SHA))


def test_v5_does_not_honour_a_revoked_expired_or_superseded_allowance_and_admits_nothing_historical(ledger):
    boot,connector,installer,control,set_control=ledger
    generation3_exhausted(boot,connector,installer,control,set_control);apply_v5(installer)
    g=window_grant(boot,control,set_control,name=CAP,revision='7'*64);register(boot,payload(g,name=CAP,generation=3,sha=G3))
    ctl=control();assert allowed(boot,ctl,CAP) is True
    ctl['bolton_exceptions'][CAP]['expires_at']=0;assert allowed(boot,ctl,CAP) is False      # revoked to zero (the invalidation)
    ctl=control();ctl['grants'][CAP]['expires_at']=0;assert allowed(boot,ctl,CAP) is False
    ctl=control();ctl['bolton_exceptions'][CAP]['expires_at']=time.time()-1;assert allowed(boot,ctl,CAP) is False
    ctl=control();ctl['hard_stop_generation']=4;assert allowed(boot,ctl,CAP) is False      # a newer stop (generation 4) admits nothing
    ctl=control()
    for historical in (PROBE,OLDCAP):assert allowed(boot,ctl,historical) is False      # the consumed allowances stay dead
