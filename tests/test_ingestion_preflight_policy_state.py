"""Preflight recognition of the installed function inventory: two coherent reviewed states, bound to the execution mode; mixed or altered inventories refused; fixed reason codes only.

The database-backed lifecycle regression (original state -> preflight -> real installation path -> teardown -> fresh controller -> preflight) is in test_discovery_ingestion_operational_wrapper_pg.py
(fault policy_lifecycle). These tests exercise the decision logic exhaustively against the reviewed files without a server."""
import json,re
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage.operational_owner import Owner,WORKER,PKG

OWNER='ingestion_storage_owner';CONFIG=['search_path=pg_catalog']


def make(apply_policy=True):
    o=Owner(lambda:None,lambda e,p:events.append((e,p)),lambda:None,identity='postgres',expiry=datetime.now(timezone.utc)+timedelta(minutes=5),bindings={})
    o.apply_policy=apply_policy;return o


events=[]


def inventories():
    states,upgraded,_=Owner.reviewed_inventories(True)
    return states['ORIGINAL'],upgraded


def rows_for(bodies,owner=OWNER,config=CONFIG):
    return [(n,b,owner,list(config)) for n,b in sorted(bodies.items())]


def run(owner_obj,rows):
    owner_obj.q=lambda c,statement,params=None,*,effect=False:rows
    events.clear()
    owner_obj.verify_installed(None)


def reason(owner_obj,rows):
    with pytest.raises(ValueError) as caught:run(owner_obj,rows)
    return str(caught.value)


def legacy_verify(self,c):
    """The predecessor (master 336cd939): every function must equal worker.sql."""
    expected={}
    for match in re.finditer(r'CREATE (?:OR REPLACE )?FUNCTION public\.(\w+)\(.*?\).*?AS \$(\w*)\$(.*?)\$\2\$;',WORKER.read_text(),re.S):expected[match[1]]=match[3]
    rows=self.q(c,"SELECT p.proname,p.prosrc,r.rolname,p.proconfig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner WHERE n.nspname='public' AND p.proname=ANY(%s) ORDER BY p.proname",(list(expected),))
    if len(rows)!=len(expected) or any(body!=expected.get(n) or owner!=OWNER or config!=CONFIG for n,body,owner,config in rows):raise ValueError('INSTALLED_FUNCTION_CONTENT_CHANGED')
    self.expected_generation=1


def test_the_two_reviewed_states_are_distinct_and_differ_in_exactly_the_policy_functions():
    original,upgraded=inventories()
    policy={m[1] for m in Owner.FUNCTION_PATTERN.finditer((PKG/'successor-policy.sql').read_text())}
    assert policy=={'ingestion_bolton_allowed','ingestion_register_bolton_exception'} and {n for n in original if original[n]!=upgraded[n]}==policy and len(original)==6


def test_the_original_state_is_recognised_in_both_modes():
    original,_=inventories()
    for mode in (True,False):
        o=make(mode);run(o,rows_for(original))
        assert o.preflight_report['policy_state']=='ORIGINAL' and o.preflight_report['reason_code']=='POLICY_STATE_RECOGNISED' and o.expected_generation==1
    assert events[-1][1]['policy_state']=='ORIGINAL'


def test_the_upgraded_state_is_recognised_only_for_a_mode_that_applies_the_policy():
    _,upgraded=inventories()
    o=make(True);run(o,rows_for(upgraded))
    assert o.preflight_report==dict(reason_code='POLICY_STATE_RECOGNISED',policy_state='SUCCESSOR_POLICY_APPLIED',permitted_states=['ORIGINAL','SUCCESSOR_POLICY_APPLIED']) and o.expected_generation==1
    refused=make(False)
    assert reason(refused,rows_for(upgraded))=='INSTALLED_POLICY_STATE_NOT_PERMITTED_FOR_MODE' and refused.preflight_report['policy_state']=='SUCCESSOR_POLICY_APPLIED' and refused.expected_generation==0


@pytest.mark.parametrize('flip',['ingestion_bolton_allowed','ingestion_register_bolton_exception'])
def test_a_mixed_inventory_is_refused_even_though_each_body_is_individually_reviewed(flip):
    original,upgraded=inventories()
    mixed={**upgraded,flip:original[flip]}
    for mode in (True,False):
        o=make(mode);assert reason(o,rows_for(mixed))=='INSTALLED_POLICY_STATE_MIXED' and o.preflight_report['policy_state']=='UNRECOGNISED'
    assert reason(make(True),rows_for({**original,flip:upgraded[flip]}))=='INSTALLED_POLICY_STATE_MIXED'


def test_an_altered_body_is_refused_in_either_state():
    original,upgraded=inventories()
    for base in (original,upgraded):
        for name in base:
            altered={**base,name:base[name]+' '}
            assert reason(make(True),rows_for(altered))=='INSTALLED_FUNCTION_CONTENT_CHANGED'


def test_a_missing_or_unknown_function_set_is_refused():
    original,_=inventories()
    assert reason(make(True),rows_for({k:v for k,v in original.items() if k!='ingestion_raise_stop'}))=='INSTALLED_FUNCTION_CONTENT_CHANGED'
    assert reason(make(True),rows_for({**original,'ingestion_extra':'x'}))=='INSTALLED_FUNCTION_CONTENT_CHANGED'


def test_ownership_and_search_path_are_still_enforced_for_every_function_in_both_states():
    original,upgraded=inventories()
    for base in (original,upgraded):
        assert reason(make(True),rows_for(base,owner='postgres'))=='INSTALLED_FUNCTION_OWNER_OR_CONFIG_CHANGED'
        assert reason(make(True),rows_for(base,config=['search_path=public']))=='INSTALLED_FUNCTION_OWNER_OR_CONFIG_CHANGED'
        assert reason(make(True),rows_for(base,config=[]))=='INSTALLED_FUNCTION_OWNER_OR_CONFIG_CHANGED'
        one=rows_for(base);one[2]=(one[2][0],one[2][1],'postgres',CONFIG)
        assert reason(make(True),one)=='INSTALLED_FUNCTION_OWNER_OR_CONFIG_CHANGED'


def test_the_predecessor_logic_fails_on_the_upgraded_state_and_the_correction_does_not():
    _,upgraded=inventories()
    predecessor=make(True)
    predecessor.q=lambda c,statement,params=None,*,effect=False:rows_for(upgraded)
    with pytest.raises(ValueError,match='INSTALLED_FUNCTION_CONTENT_CHANGED'):legacy_verify(predecessor,None)
    run(make(True),rows_for(upgraded))            # the corrected controller accepts the very same inventory


def test_only_fixed_codes_and_a_policy_state_are_exported():
    original,upgraded=inventories()
    codes=set()
    for case in (rows_for(original),rows_for(upgraded),rows_for({**upgraded,'ingestion_bolton_allowed':original['ingestion_bolton_allowed']}),rows_for(original,owner='x')):
        o=make(True)
        try:run(o,case)
        except ValueError:pass
        codes.add(o.preflight_report['reason_code'])
        report=json.dumps(o.preflight_report)
        assert not re.search(r'postgres|SELECT|\$\$|CREATE',report)
    assert codes<={'POLICY_STATE_RECOGNISED','INSTALLED_POLICY_STATE_MIXED','INSTALLED_FUNCTION_OWNER_OR_CONFIG_CHANGED'} and len(codes)==3
    assert Owner(lambda:None,lambda *_:None,lambda:None,expiry=datetime.now(timezone.utc),bindings={}).accounting()['preflight']['reason_code']=='NOT_REACHED'


def test_a_duplicated_overload_with_a_missing_function_is_refused_with_a_fixed_code_not_a_crash():
    original,_=inventories()
    rows=rows_for(original)
    dup=[r for r in rows if r[0]!='ingestion_raise_stop']+[rows[0]]            # same row count as expected, but one function missing and one duplicated
    assert len(dup)==len(rows)
    o=make(True)
    assert reason(o,dup)=='INSTALLED_FUNCTION_CONTENT_CHANGED' and o.preflight_report['reason_code']=='INSTALLED_FUNCTION_CONTENT_CHANGED'
