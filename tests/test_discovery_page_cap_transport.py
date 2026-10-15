"""Offline UI enumeration -> real transport classifier -> reader -> recovery.

The browser is a finite locator double; no source/DB calls or historical edits.
"""
import asyncio
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from verification.direct_reference import instrumented_probe as transport
from verification.discovery import r0_recovery_proposal as recovery
from verification.discovery import finite_acceptance as finite
from verification.discovery.arcus_ui_config import dated_config, UI_CASES
from verification.discovery.arcus_ui_window import enumerate_ui
from tests.test_discovery_r0_recovery_proposal import evidence
from tests.test_discovery_arcus_ui import card


class Page:
    def __init__(self, config):
        self.config=config; self.segment=0
    def locator(self, selector):
        page=self
        class Locator:
            async def wait_for(self, **kw): pass
            async def inner_text(self, **kw):
                return f'Showing {page.segment*10+1} to {page.segment*10+10} of 73 results'
            def filter(self, **kw): return self
            async def count(self): return 0 if selector=='p:text-is("No results found")' else 1
            async def get_attribute(self, name): return '#'
            async def click(self, **kw): page.segment+=1
        return Locator()
    def get_by_label(self, label, exact=True):
        page=self
        class Label:
            async def input_value(self, **kw):
                from datetime import date
                if label=='Valid date from':return date.fromisoformat(page.config.start).strftime('%d/%m/%Y')
                if label=='Valid date to':return date.fromisoformat(page.config.end).strftime('%d/%m/%Y')
                return ''
        return Label()
    def get_by_role(self, role, name, exact=True):
        class Role:
            async def click(self, **kw): pass
            async def inner_text(self, **kw):return 'Planning Applications' if name=='Category' else 'Select an option'
        return Role()


def capped_transport(row):
    config=dated_config(UI_CASES['discovery_manchester_ui_window'],row['start'],row['end'])
    page=Page(config);audit=evidence(row);stopped=asyncio.Event()
    async def cards(page, config):
        return [card(ref=f'TEST/{page.segment*10+i:03}',key=f'a1DSl00000{page.segment*10+i:08}',valid=__import__('datetime').date.fromisoformat(config.start).strftime('%d/%m/%Y')) for i in range(10)]
    with patch('verification.discovery.arcus_ui_window.read_cards',cards):
        task=enumerate_ui(page,audit,stopped,config)
        with pytest.raises(StopIteration): task.send(None)
    def fail(code):transport.record_failure(audit,code);stopped.set()
    transport.classify_ui_enumeration(audit,fail)
    return audit


@pytest.fixture(autouse=True)
def credential_free(monkeypatch):monkeypatch.delenv('DATABASE_URL',raising=False)


def test_actual_transport_boundary_and_real_reader_continue_cap(tmp_path):
    row=recovery.PLAN['rows'][0];audit=capped_transport(row)
    assert audit['failure'] is None and not audit['safety_events']
    assert audit['listing_outcome']=='BOUNDED_PAGE_CAP' and len(audit['listing_records'])==60
    calls=[]
    def supervised(case,path,**kw):
        calls.append(case);path.write_text(json.dumps(audit))
    def reader(current):
        return finite.read(current) if not calls else evidence(current)
    with patch.object(transport,'supervised',supervised):
        result=recovery.execute(recovery.PLAN,recovery.PLAN_HASH,reader=reader,clock=lambda:0)
    assert len(result['results'])==28 and not result['not_attempted']
    first=result['results'][0]
    assert first['safe_local_gap'] and first['enumeration_completeness']=='INCOMPLETE'
    assert len(first['source']['listing_records'])==60
    assert result['completeness']=='INCOMPLETE' and not result['completed_through_advanced']
    # This helper is called at the actual post-enumeration transport boundary.
    assert 'classify_ui_enumeration(audit, fail)' in inspect.getsource(transport.probe)


@pytest.mark.parametrize('change',[
 {'failure':'SOURCE_EXCEPTION'}, {'safety_failure':True}, {'safety_events':['ORIGIN_DENIED']},
 {'listing_failure':'ValueError:date outside interval'}, {'destination':'https://wrong.invalid/'},
 {'requested_interval':['2026-01-01','2026-01-02']}, {'applied_interval':None},
 {'cleanup':'FAILED'}, {'process_cleanup':'UNKNOWN'}, {'live_owned_survivors':1},
 {'requests':None}, {'accounting_complete':False},
 {'listing_records':[{'reference':None,'source_record_id':'X'}]},
])
def test_mutated_hard_failure_never_reaches_second_source(change):
    row=recovery.PLAN['rows'][0];audit=capped_transport(row);audit.update(deepcopy(change))
    transport.classify_ui_enumeration(audit,lambda code:transport.record_failure(audit,code))
    calls=[]
    def reader(_):calls.append(1);return audit
    result=recovery.execute(recovery.PLAN,recovery.PLAN_HASH,reader=reader,clock=lambda:0)
    assert len(calls)==1 and len(result['not_attempted'])==27
    assert result['stop_reason'] in {'SAFETY_OR_UNCLASSIFIED_FAILURE','RESOURCE_ACCOUNTING'}
    assert result['completeness']=='INCOMPLETE'


def test_missing_total_is_not_reinterpreted_as_safe_arcus_cap():
    audit=capped_transport(recovery.PLAN['rows'][0])
    audit.update(enumeration_evidence='TOTAL_UNKNOWN',listing_failure='ValueError:page marker')
    transport.classify_ui_enumeration(audit,lambda code:transport.record_failure(audit,code))
    assert audit['failure']=='LISTING_NOT_QUALIFIED' and audit['safety_failure']


def test_retained_ordinary_idox_missing_total_already_continues():
    # Use actual retained Bury source shape, not an idealised clean failure flag.
    old=json.loads(Path('tests/fixtures/discovery/r0-bury-total-unknown.json').read_text())
    source=deepcopy(old['source'])
    assert source['enumeration_evidence']=='TOTAL_UNKNOWN' and source.get('failure') is None
    row=old['window']
    assert recovery.safety(row,source) and recovery.local_gap(row,source)


def test_consumed_artifact_remains_byte_identical_and_not_rewritten():
    import zipfile
    fixture=Path('tests/fixtures/discovery/r0-recovery-38744118357.zip')
    before=fixture.read_bytes()
    assert hashlib.sha256(before).hexdigest()=='143828a4d725bcdae5f086dfc6c617bcc4d62777f42b0808f01b2304f3a98ea7'
    with zipfile.ZipFile(fixture) as z:
        consumed=json.loads(z.read('round.json'))['results'][0]['source']
    assert consumed['failure']=='LISTING_NOT_QUALIFIED' and consumed['safety_failure']
    # New results are generated by the corrected boundary, never by editing the
    # consumed audit or clearing its recorded flags.
    fresh=capped_transport(recovery.PLAN['rows'][0])
    assert fresh['failure'] is None and fixture.read_bytes()==before
