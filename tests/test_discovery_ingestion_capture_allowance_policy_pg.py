"""Policy v4 (generation-2 capture acceptance) on a REAL disposable PostgreSQL 17 with the real installed ledger, the reviewed 18 October successor policy and then policy v3, exactly as in production. Verifies: the
two named allowances register in the exact observed stop state even with the cap of three exception keys exhausted; nothing else is admitted (cap unchanged for every other name, every other state refused);
re-registration is impossible; historical entries are untouched; only the two function definitions change. Loopback only."""
import json
import time

import psycopg
import pytest

from verification.ingestion_storage import operational_runner as orr
from tests.test_discovery_ingestion_policy_generation2_pg import (ledger,observed_state,probe_grant,payload,register,allowed,apply_v3,function_fingerprints,memberships,IDOX,STOP1_SHA,STOP2_SHA,NAMED as PROBE)

CAP=orr.CAPTURE_AUTHORITY+'_CAPTURE'
SCR=orr.CAPTURE_AUTHORITY+'_SCREEN'
V4=orr.GENERATION2_CAPTURE_POLICY


def apply_v4(installer):
    with installer.connection() as c:installer.script(c,V4)


def exhausted_state(boot,connector,installer,control,set_control):
    """The state production is in now: v3 installed, generation 2, two revoked historical exceptions plus the CONSUMED (revoked) probe exception = three keys."""
    observed_state(set_control,control);grant=probe_grant(boot,control,set_control)
    apply_v3(installer);register(boot,payload(grant))
    ctl=control();ctl['grants'][PROBE]['expires_at']=0;ctl['bolton_exceptions'][PROBE]['expires_at']=0;set_control(ctl)
    assert len(control()['bolton_exceptions'])==3
    return control()


def test_under_v3_the_exhausted_cap_refuses_a_fourth_exception(ledger):
    boot,connector,installer,control,set_control=ledger
    exhausted_state(boot,connector,installer,control,set_control)
    grant=probe_grant(boot,control,set_control,name=CAP,revision='8'*64)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant,name=CAP))      # v3: the problem being solved


def test_v4_registers_exactly_the_two_named_allowances_with_the_cap_exhausted_and_touches_nothing_else(ledger):
    boot,connector,installer,control,set_control=ledger
    before_ctl=exhausted_state(boot,connector,installer,control,set_control)
    before_fn=function_fingerprints(boot);before_members=memberships(boot)
    apply_v4(installer)
    after_fn=function_fingerprints(boot)
    assert sorted(k for k in before_fn if before_fn[k]!=after_fn.get(k))==['ingestion_bolton_allowed','ingestion_register_bolton_exception'] and set(before_fn)==set(after_fn)      # exactly the two functions
    assert memberships(boot)==before_members and control()==before_ctl      # nothing else; the control record is byte-for-byte unchanged by the installation
    g_cap=probe_grant(boot,control,set_control,name=CAP,revision='8'*64)
    e_cap=register(boot,payload(g_cap,name=CAP))
    assert e_cap['authority']==CAP and e_cap['hard_stop_generation']==2
    ctl=control();assert allowed(boot,ctl,CAP) is True and len(ctl['bolton_exceptions'])==4      # the cap was 3: the named exemption, only
    g_scr=probe_grant(boot,control,set_control,name=SCR,revision='7'*64)
    g_scr['source_calls']=0
    ctl=control();ctl['grants'][SCR]['source_calls']=0;set_control(ctl)
    e_scr=register(boot,payload(dict(g_scr),name=SCR))
    ctl=control();assert allowed(boot,ctl,SCR) is True and len(ctl['bolton_exceptions'])==5 and ctl['hard_stop_generation']==2 and ctl['manual_stop']==IDOX and ctl['last_hard_stop']==IDOX      # generation untouched
    for name in ('HISTORICAL_0','HISTORICAL_1'):assert ctl['bolton_exceptions'][name]==before_ctl['bolton_exceptions'][name] and ctl['grants'][name]==before_ctl['grants'][name]      # history preserved
    assert ctl['bolton_exceptions'][PROBE]==before_ctl['bolton_exceptions'][PROBE] and ctl['grants'][PROBE]==before_ctl['grants'][PROBE]
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(g_cap,name=CAP))      # a name that exists can never be registered again


def test_v4_keeps_the_cap_for_every_other_name_and_state(ledger):
    boot,connector,installer,control,set_control=ledger
    exhausted_state(boot,connector,installer,control,set_control);apply_v4(installer)
    # another name at generation 2: refused by the stop predicate and by the cap
    grant=probe_grant(boot,control,set_control,name='SOME_OTHER_ALLOWANCE',revision='6'*64)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant,name='SOME_OTHER_ALLOWANCE'))
    # the cap in isolation: the ORDINARY generation-1 path with three keys present is still refused for any name (the exemption never reaches it)
    ctl=control();ctl['hard_stop_generation']=1;ctl['last_hard_stop']='OPERATIONAL_FIRST_CONNECTION_FAILURE_CLEANUP_20261018';ctl['manual_stop']='STORAGE_TEST_STOP';set_control(ctl)
    grant=probe_grant(boot,control,set_control,name='ANOTHER_GEN1_ALLOWANCE',revision='5'*64)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant,name='ANOTHER_GEN1_ALLOWANCE',generation=1,sha=STOP1_SHA))
    assert allowed(boot,control(),'SOME_OTHER_ALLOWANCE') is False


@pytest.mark.parametrize('name',[CAP,SCR])
@pytest.mark.parametrize('state',['generation_1','generation_3','other_manual_stop','other_last_hard_stop','absent_manual_stop','absent_generation','wrong_digest'])
def test_v4_refuses_the_new_names_in_any_state_but_the_exact_observed_one(ledger,name,state):
    boot,connector,installer,control,set_control=ledger
    exhausted_state(boot,connector,installer,control,set_control);apply_v4(installer)
    ctl=control();sha=STOP2_SHA;generation=2
    if state=='generation_1':ctl['hard_stop_generation']=1;generation=1
    if state=='generation_3':ctl['hard_stop_generation']=3
    if state=='other_manual_stop':ctl['manual_stop']='SOMETHING_ELSE'
    if state=='other_last_hard_stop':ctl['last_hard_stop']='SOMETHING_ELSE'
    if state=='absent_manual_stop':ctl.pop('manual_stop')
    if state=='absent_generation':ctl.pop('hard_stop_generation')
    if state=='wrong_digest':sha='0'*64
    set_control(ctl)
    grant=probe_grant(boot,control,set_control,name=name,revision='4'*64)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant,name=name,generation=generation,sha=sha))


def test_v4_does_not_honour_a_revoked_or_expired_new_allowance_and_the_probe_branch_is_unchanged(ledger):
    boot,connector,installer,control,set_control=ledger
    exhausted_state(boot,connector,installer,control,set_control);apply_v4(installer)
    g_cap=probe_grant(boot,control,set_control,name=CAP,revision='8'*64);register(boot,payload(g_cap,name=CAP))
    ctl=control();assert allowed(boot,ctl,CAP) is True
    ctl['bolton_exceptions'][CAP]['expires_at']=0;assert allowed(boot,ctl,CAP) is False      # revoked to zero (the invalidation): no longer honoured
    ctl=control();ctl['grants'][CAP]['expires_at']=0;assert allowed(boot,ctl,CAP) is False      # the grant revoked: the binding no longer matches
    ctl=control();ctl['bolton_exceptions'][CAP]['expires_at']=time.time()-1;assert allowed(boot,ctl,CAP) is False      # expired
    ctl=control();ctl['hard_stop_generation']=3;assert allowed(boot,ctl,CAP) is False      # a newer stop (generation 3) admits nothing
    ctl=control();assert allowed(boot,ctl,PROBE) is False      # the consumed probe entry is revoked and stays so


@pytest.mark.parametrize('name',[CAP,SCR])
def test_v4_cap_exemption_needs_generation_2_even_where_the_ordinary_path_would_otherwise_pass(ledger,name):
    boot,connector,installer,control,set_control=ledger
    exhausted_state(boot,connector,installer,control,set_control);apply_v4(installer)
    ctl=control();ctl['hard_stop_generation']=1;ctl['last_hard_stop']='OPERATIONAL_FIRST_CONNECTION_FAILURE_CLEANUP_20261018';ctl['manual_stop']='STORAGE_TEST_STOP';set_control(ctl)
    grant=probe_grant(boot,control,set_control,name=name,revision='3'*64)
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant,name=name,generation=1,sha=STOP1_SHA))      # the cap holds: the exemption is conditioned on the bound generation-2 state
    ctl=control();ctl.pop('hard_stop_generation');set_control(ctl)      # an absent generation is NULL: it must refuse, never widen
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):register(boot,payload(grant,name=name,generation=1,sha=STOP1_SHA))
