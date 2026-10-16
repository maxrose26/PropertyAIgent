"""Offline only. Synthetic DOM doubles are explicitly not fresh council evidence."""
import asyncio
from dataclasses import replace
from copy import deepcopy
from unittest.mock import patch
import pytest,requests
from verification.discovery import arcus_ui_window as ui
from verification.discovery.arcus_ui_config import MANCHESTER,dated_config
from verification.discovery.idox_window import WindowConfig,run
from verification.discovery.arcus_ui_audit import validate
from verification.direct_reference.instrumented_probe import classify_ui_enumeration
from tests.test_discovery_r0_recovery_proposal import evidence
from tests.test_discovery_page_cap_transport import Page
from tests.test_discovery_idox_window import Response
from verification.bolton_recon.fixtures import FORM


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    for key in ('DATABASE_URL','COMMITTEE_DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY'):
        monkeypatch.delenv(key,raising=False)


def sync_await(coro):
    # All synthetic locators complete immediately; no event loop/network sockets.
    try:coro.send(None)
    except StopIteration as done:return done.value
    raise AssertionError('synthetic locator unexpectedly scheduled IO')


def test_metadata_textcontent_without_layout_newline_is_captured_and_private_fields_ignored():
    class Leaf:
        def __init__(self,texts,href=None): self.texts=texts;self.href=href
        async def count(self):return len(self.texts)
        async def inner_text(self,**kw):assert len(self.texts)==1;return self.texts[0]
        async def get_attribute(self,*a,**kw):return self.href
    class Items:
        texts=['Reference\nTEST/1','Valid Date\n01/10/2026','Description\n49 dwellings','Site Address\nTest site','Applicant\nPRIVATE_CONTACT']
        async def count(self):return len(self.texts)
        def filter(self,has_text):return Leaf([v for v in self.texts if has_text.search(v.replace('\n',''))])
    class Card:
        def locator(self,s):
            if s=='[role="listitem"]':return Items()
            assert s=='a[href*="/detail/"]'
            return Leaf(['TEST/1'],'/pr/s/detail/'+('a'*18)+'?c__r=Arcus_BE_Public_Register')
    class Cards:
        async def count(self):return 1
        def nth(self,i):assert i==0;return Card()
    class P:
        def locator(self,s):assert s=='div[role="list"].slds-box';return Cards()
    cfg=replace(MANCHESTER,start='2026-10-01',end='2026-10-03',capture_metadata=True)
    cards=sync_await(ui.read_cards(P(),cfg))
    row=ui.qualify_segment('Showing 1 to 1 of 1 results',cards,1,config=cfg)[3][0]
    assert row['fields']['proposal']['value']=='49 dwellings'
    assert row['fields']['application_type']['state']=='UNKNOWN'
    assert row['metadata_capture_evidence']['label_counts']['Description']==1
    assert 'PRIVATE_CONTACT' not in str(row)
    # Default reference/date-only mode remains unchanged.
    old=sync_await(ui.read_cards(P(),replace(cfg,capture_metadata=False)))
    assert [x['label'] for x in old[0]['fields']]==['Reference','Valid Date']


def zero_source(*,wrong_date=False,conflict=None):
    row=dict(council='manchester',start='2026-10-15',end='2026-10-15',semantics='VALIDATED')
    config=dated_config(MANCHESTER,row['start'],row['end']);a=evidence(row)
    class P(Page):
        def locator(self,selector):
            old=super().locator(selector)
            class L:
                async def wait_for(self,**kw):return None
                async def count(self):
                    return 1 if selector=='p:text-is("No results found")' or selector==conflict else 0
                async def inner_text(self,**kw):return 'No results found'
                def filter(self,**kw):return self
            return L()
        def get_by_label(self,label,exact=True):
            if wrong_date and label=='Valid date to':
                class Bad:
                    async def input_value(self,**kw):return '14/10/2026'
                return Bad()
            return super().get_by_label(label,exact)
    sync_await(ui.enumerate_ui(P(config),a,asyncio.Event(),config))
    classify_ui_enumeration(a,lambda reason:a.update(failure=reason,safety_failure=True))
    return row,config,a


def test_explicit_zero_through_worker_classifier_and_real_parent():
    from verification.discovery import r0_recovery_proposal as parent,finite_acceptance as f
    row,config,a=zero_source()
    assert validate(a,config)['records']==0
    assert f.classify(row,a)=='COMPLETE'
    plan=dict(rows=[row]);out=parent._execute_fixed(plan,'synthetic',reader=lambda _:a,limits=dict(calls=1,requests=80,bytes=20*1024*1024,seconds=55,output_bytes=20000000),checkpoint=lambda _:None,clock=lambda:0)
    assert out['results'][0]['enumeration_completeness']=='COMPLETE'
    assert out['results'][0]['source']['listing_records']==[]
    for change in [{'explicit_zero_evidence':None},{'applied_interval':None},{'safety_events':['WRONG_ORIGIN']},{'live_owned_survivors':1}]:
        with pytest.raises(ValueError):validate(dict(a,**change),config)


@pytest.mark.parametrize('options',[dict(wrong_date=True),dict(conflict='div[role="list"].slds-box'),dict(conflict='p.pr-pagination__results'),dict(conflict='a.pr-pagination__link')])
def test_zero_requires_positive_criteria_and_no_contradiction(options):
    _,_,a=zero_source(**options)
    assert a['enumeration_evidence'] is None and a['failure']


@pytest.mark.parametrize('failure',[requests.Timeout('PRIVATE'),requests.ConnectionError('PRIVATE'),502,503,504])
def test_actual_idox_boundary_no_retry_policy_stops_first_attempt(failure):
    calls=[];responses=[]
    def dispatch(*a,**kw):
        calls.append(1)
        if isinstance(failure,Exception):raise failure
        response=Response(b'upstream error');response.status_code=failure;responses.append(response);return response
    out=run(dispatch,WindowConfig('bury',max_transport_retries=0))
    assert len(calls)==1 and out['resource']['requests_attempted']==1 and out['resource']['retries']==0
    assert out['failure'] and out['cleanup']=='BOUNDARY_CLOSED'
    assert all(x.closed for x in responses) and 'PRIVATE' not in str(out)


def test_retry_default_legacy_and_invalid_policy():
    assert WindowConfig('bury').max_transport_retries==1
    for value in [True,-1,2,'0']:
        with pytest.raises(ValueError):WindowConfig('bury',max_transport_retries=value)


def test_oldham_sort_failure_still_fails_closed_and_exports_no_html():
    bodies=iter([FORM,b'<html><form><input value="PRIVATE_CONTACT"></form></html>'])
    a=run(lambda *args,**kw:Response(next(bodies)),WindowConfig('oldham',max_transport_retries=0))
    assert a['failure']=='ListingError:sort selector'
    assert a['failure_diagnostic']['counts']['order_by_selects']==0
    assert a['applied_interval'] is None and a['records']==[]
    assert 'PRIVATE_CONTACT' not in str(a)


def test_no_retry_actual_reader_child_config_boundary_wiring(tmp_path):
    from verification.discovery import finite_acceptance as f
    import json,sys
    calls=[]
    def supervised(command,**kw):
        calls.append((command,kw))
        assert '--no-transport-retry' in command
        def source(config):
            assert config.max_transport_retries==0
            return run(lambda *a,**k:(_ for _ in ()).throw(requests.Timeout('SYNTHETIC')),config)
        with patch.object(sys,'argv',command[2:]),patch.object(f,'live',source):f.main()
        return 0,False
    with patch.object(f,'supervise',supervised):
        out=f.read(dict(council='wigan',start='2026-10-15',end='2026-10-15',semantics='RECEIVED'),no_transport_retry=True)
    assert len(calls)==1 and out['resource']['requests_attempted']==1
    assert out['resource']['retries']==0 and out['resource']['retry_policy']=='NO_INTERNAL_RETRY'
    assert set(calls[0][1]['env'])=={'PATH','HOME','TMPDIR','PYTHONDONTWRITEBYTECODE'}


def test_metadata_diagnostic_is_strict_bounded_and_cannot_export_payload():
    safe=dict(version=1,row_item_count=6,label_counts={k:0 for k in ui.METADATA_LABELS},route='VISIBLE_ROW_EXACT_RENDERED_LABEL_V2')
    assert ui.metadata_capture_evidence(safe)==safe
    for mutation in [dict(safe,raw_html='PRIVATE'),dict(safe,row_item_count=21),dict(safe,label_counts={'Applicant':1}),dict(safe,label_counts=dict(safe['label_counts'],Description=True))]:
        with pytest.raises(ValueError,match='metadata evidence shape'):ui.metadata_capture_evidence(mutation)


@pytest.mark.parametrize('council',['rochdale','salford'])
def test_unobserved_councils_do_not_acquire_manchester_zero_shape(council):
    from verification.discovery.arcus_ui_config import UI_CASES
    from playwright.async_api import TimeoutError as LocatorTimeout
    cfg=dated_config(UI_CASES['discovery_'+council+'_ui_window'],'2026-10-15','2026-10-15');seen=[];a={}
    class P:
        def locator(self,selector):
            seen.append(selector)
            class L:
                async def wait_for(self,**kw):raise LocatorTimeout('synthetic')
            return L()
    sync_await(ui.enumerate_ui(P(),a,asyncio.Event(),cfg))
    assert seen==['p.pr-pagination__results'] and a['enumeration_evidence'] is None
    assert a['applied_interval'] is None


def test_zero_consumer_rejects_other_council_even_with_copied_proof():
    from verification.discovery.arcus_ui_config import ROCHDALE
    _,_,a=zero_source();cfg=dated_config(ROCHDALE,'2026-10-15','2026-10-15')
    a.update(case='discovery_rochdale_ui_window',destination=cfg.destination)
    with pytest.raises(ValueError,match='zero evidence'):validate(a,cfg)
