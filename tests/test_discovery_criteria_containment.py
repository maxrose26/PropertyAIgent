"""Actual async locator -> transport classifier -> recovery caller, synthetic."""
import asyncio,json,os
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import pytest
from playwright.async_api import TimeoutError as LocatorTimeout
from verification.discovery import r0_exact16 as x
from verification.discovery import r0_recovery_proposal as r
from verification.discovery import arcus_ui_window as ui
from verification.direct_reference.instrumented_probe import classify_ui_enumeration,record_failure
from tests.test_discovery_r0_recovery_proposal import evidence


def timeout_source(row,exc=LocatorTimeout('SYNTHETIC')):
    a=evidence(row)
    class Locator:
        async def wait_for(self,**kwargs):raise exc
    class Page:
        def locator(self,_):return Locator()
    class Stop:
        def is_set(self):return False
    config=x.finite.dated_config(x.finite.UI_CASES['discovery_'+row['council']+'_ui_window'],row['start'],row['end'])
    task=ui.enumerate_ui(Page(),a,Stop(),config)
    try:task.send(None)
    except StopIteration:pass
    a.update(destination=config.destination,requested_origins=['https://'+config.host],navigated_origins=['https://'+config.host],
        blocked_actions=[],blocked_action_metadata=[],blocked_posts=0,navigation_mismatch=None,containment_accounting_verified=True,accounting_complete=True)
    classify_ui_enumeration(a,lambda reason:record_failure(a,reason))
    return a


@pytest.fixture(autouse=True)
def clean(monkeypatch):monkeypatch.delenv('DATABASE_URL',raising=False)


def execute(reader,checkpoint=lambda _:None):
    return r._execute_fixed(json.loads(x.MANIFEST.read_bytes()),x.MANIFEST_SHA,reader=reader,limits=x.PROFILE,checkpoint=checkpoint,clock=lambda:0,containment=True)


def test_typed_timeout_quarantines_only_council_after_checkpoint():
    calls=[];sealed=[]
    def reader(row):
        if calls:assert sealed
        calls.append(row);return timeout_source(row) if len(calls)==1 else evidence(row)
    out=execute(reader,sealed.append)
    assert len(calls)==13 and calls[1]['council']=='stockport'
    assert len(out['quarantined_windows'])==3 and all(v['outcome']=='NOT_ATTEMPTED_COUNCIL_QUARANTINED' for v in out['quarantined_windows'])
    assert out['completeness']=='INCOMPLETE' and out['results'][0]['enumeration_completeness']=='FAILED'
    assert out['results'][0]['source_local_contained'] and out['results'][0]['source']['applied_interval'] is None


@pytest.mark.parametrize('change',[{'failure':'SECURITY'},{'safety_events':['ORIGIN_DENIED']},{'safety_failure':True},
    {'destination':'https://wrong.invalid/'},{'process_cleanup':'UNKNOWN'},{'live_owned_survivors':1},
    {'accounting_complete':False},{'containment_accounting_verified':False},{'requested_origins':[]},{'blocked_actions':['unexpected']},
    {'applied_interval':['2026-09-17','2026-09-23']},{'listing_stage':'SORT_SELECTOR'},
    {'criteria_control_timeout':{'code':ui.LOCAL_TIMEOUT,'operation':'UNKNOWN','exception_contract':'PLAYWRIGHT_LOCATOR_TIMEOUT_V1'}}])
def test_hard_failure_mutations_stop_before_next_call(change):
    calls=[]
    def reader(row):calls.append(row);return dict(timeout_source(row),**change)
    out=execute(reader);assert len(calls)==1 and out['stop_reason']


def test_generic_timeout_never_qualifies_and_checkpoint_failure_stops():
    calls=[]
    out=execute(lambda row:calls.append(row) or timeout_source(row,TimeoutError('generic')))
    assert len(calls)==1 and not out['results'][0]['source_local_contained']
    calls=[]
    def broken(_):raise ValueError('checkpoint')
    out=execute(lambda row:calls.append(row) or timeout_source(row),broken)
    assert len(calls)==1 and out['stop_reason']=='CHECKPOINT_FAILURE_NO_NEXT_CALL'


def test_actual_source_worker_clean_environment_and_new_context(tmp_path):
    from verification.discovery import finite_acceptance as f
    seen=[]
    def run(command,**kw):
        seen.append((command,kw));Path(command[-1]).write_text('{}');return 0,False
    with patch.object(f,'supervise',side_effect=run):
        rows=json.loads(x.MANIFEST.read_bytes())['rows'];f.read(rows[4]);f.read(rows[8])
    assert seen[0][1]['env']['HOME']!=seen[1][1]['env']['HOME']
    assert not any('DATABASE' in k for _,kw in seen for k in kw['env'])
