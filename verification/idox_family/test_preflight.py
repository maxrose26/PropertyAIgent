"""Source-inspection rehearsals only; frozen code + synthetic page, no scraper."""
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urljoin,urlsplit
import socket
import pytest
import yaml
from bs4 import BeautifulSoup
from verification.da0.contracts import GATES,VERSION,validate_registry

ROOT=Path(__file__).resolve().parents[2]
LEDGER=ROOT/'docs/design/idox-family-preflight/EVIDENCE.json'
EXCERPT=Path(__file__).with_name('retained_collect_result_links.py.txt')


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args,**kwargs):raise AssertionError('offline preflight cannot contact sources')
    monkeypatch.setattr(socket.socket,'connect',denied)
    monkeypatch.setattr(socket,'create_connection',denied)
    monkeypatch.setattr(socket,'getaddrinfo',denied)


def ledger():return json.loads(LEDGER.read_text())


def collector():
    # Only a pinned trusted repository function is executed; never source HTML/code.
    assert hashlib.sha256(EXCERPT.read_bytes()).hexdigest()==ledger()['source_code_provenance']['excerpt_sha256']
    tree=ast.parse(EXCERPT.read_text())
    assert len(tree.body)==1 and isinstance(tree.body[0],ast.FunctionDef)
    assert tree.body[0].name=='collect_result_links'
    prefix=ast.parse('from __future__ import annotations').body
    tree.body=prefix+tree.body;ast.fix_missing_locations(tree)
    scope={'BeautifulSoup':BeautifulSoup,'urljoin':urljoin,'_goto_with_retry':lambda p,u:None,
           'is_rate_limited':lambda h:'too many requests' in h.lower(),
           'WAIT_SECONDS':0,'time':SimpleNamespace(sleep=lambda _:None)}
    exec(compile(tree,'trusted-retained-function','exec'),scope)
    return scope['collect_result_links']


class Page:
    def __init__(self,pages,*,fail_next=False,repeat=False,select_failure=False):
        self.pages=pages;self.index=0;self.url='https://fixture.invalid/online-applications/advancedSearchResults.do'
        self.fail_next=fail_next;self.repeat=repeat;self.select_failure=select_failure
        self.filled=[];self.transitions=0
    def fill(self,selector,value):self.filled.append((selector,value))
    def click(self,selector):assert selector=='input[value="Search"]'
    def wait_for_load_state(self,*a,**k):pass
    def select_option(self,*a):
        if self.select_failure:raise LookupError('synthetic missing control')
    def content(self):return self.pages[self.index]
    def locator(self,*a,**k):return Next(self)


class Next:
    def __init__(self,page):self.page=page;self.first=self
    def count(self):return int(self.page.repeat or self.page.index+1<len(self.page.pages))
    def click(self):
        self.page.transitions+=1
        if self.page.fail_next or self.page.transitions>=3:
            # Synthetic stop prevents the legacy unbounded loop in this test only.
            raise TimeoutError('synthetic stop, not runtime cancellation proof')
        if not self.page.repeat:self.page.index+=1


def html(key,tab='summary'):
    return '<html><a href="applicationDetails.do?activeTab='+tab+'&keyVal='+key+'">Synthetic identity</a></html>'


def council(mode='received'):
    stem='Validated' if mode=='validated' else 'Received'
    return SimpleNamespace(search_url='https://fixture.invalid/online-applications/search.do',
                           date_start_field='date(application'+stem+'Start)',date_end_field='date(application'+stem+'End)')


def test_cohort_reconciles_registry_and_actual_configuration():
    e=ledger();conf=yaml.safe_load((ROOT/'config/councils.yaml').read_text())['councils']
    expected={k for k,v in conf.items() if v['doc_system'] in {'idox','idox_anite'}}
    rows={x['council']:x for x in e['cohort']}
    assert set(rows)==expected=={'bolton','bury','oldham','stockport','tameside','trafford','wigan'}
    registry={r['source_id']:validate_registry(r) for r in json.loads((ROOT/'verification/da0/registry_fixtures.json').read_text())['records']}
    for code,row in rows.items():
        assert row['origin']==conf[code]['base_url'] and row['date_kind']==conf[code]['date_field_mode']
        assert row['platform_family']==registry[row['source_id']]['platform_family']
        assert row['platform_family']==('IDOX_ANITE' if code=='bury' else 'IDOX')
        assert set(row['gates'])==GATES and set(row['gates'].values())=={'UNKNOWN'}
        assert row['operational'] is False
    assert sum(r['retained_manifest_references'] for r in rows.values())==121
    assert sum(r['retained_manifest_references'] for k,r in rows.items() if k!='oldham')==101
    assert e['operationally_supported_references']==0


@pytest.mark.parametrize('mode',['received','validated'])
def test_existing_shared_function_uses_configured_date_kind(mode):
    p=Page([html('A')]);c=council(mode)
    collector()(p,c,'01/10/2026','07/10/2026')
    assert p.filled==[(f'input[name="{c.date_start_field}"]','01/10/2026'),(f'input[name="{c.date_end_field}"]','07/10/2026')]


def test_existing_function_traverses_synthetic_next_page():
    p=Page([html('A'),html('B')]);result=collector()(p,council(),'01/10/2026','07/10/2026')
    assert len(result)==2 and p.transitions==1


def test_legacy_paging_exception_returns_partial_links_without_qualification():
    p=Page([html('A'),html('B')],fail_next=True)
    result=collector()(p,council(),'01/10/2026','07/10/2026')
    assert len(result)==1 and 'keyVal=A' in result[0]  # defect evidence, not desired contract


def test_legacy_duplicate_page_has_no_loop_guard():
    p=Page([html('A')],repeat=True)
    result=collector()(p,council(),'01/10/2026','07/10/2026')
    assert len(result)==1 and p.transitions==3  # stopped only by synthetic exception


def test_legacy_tabs_are_not_deduplicated_by_application_key():
    p=Page([html('A','summary')+html('A','contacts')])
    assert len(collector()(p,council(),'01/10/2026','07/10/2026'))==2


def test_legacy_link_substring_does_not_enforce_origin():
    p=Page(['<a href="https://external.invalid/applicationDetails.do?activeTab=summary&keyVal=A">x</a>'])
    assert urlsplit(collector()(p,council(),'01/10/2026','07/10/2026')[0]).hostname=='external.invalid'


def test_legacy_missing_page_size_and_unrecognised_page_are_not_completion_proof():
    p=Page(['<html>unrecognised synthetic page</html>'],select_failure=True)
    assert collector()(p,council(),'01/10/2026','07/10/2026')==[]


def test_rate_limit_still_fails_in_legacy_function():
    with pytest.raises(RuntimeError,match='Rate limited'):
        collector()(Page(['too many requests']),council(),'01/10/2026','07/10/2026')


def test_partial_candidate_is_not_source_or_live_authority():
    e=ledger();assert e['binding_contract_version']==VERSION and e['decision']=='PARTIAL_CANDIDATE'
    assert e['execution_authority'] is None and e['transport']['new_transport_implementation'] is False
    assert e['transport']['http_date_window_path']=='UNPROVED'
    assert e['transport']['browser_byte_accounting'].startswith('UNPROVED')
    assert e['changed_discovery']['operational_classification']=='UNKNOWN'
    assert e['future_acceptance_councils']==['bolton','stockport','wigan']
    assert e['source_exceptions']['oldham'].startswith('DEFERRED')
    assert all(e[k] is False for k in ['documents_allowed','models_allowed','database_allowed'])
    assert e['live_application_requests']==e['search_submissions']==e['detail_requests']==0


def test_checkpoint_and_identity_are_qualified_not_opportunity_creation():
    e=ledger();assert 'not accepted application' in e['key_only_result']
    assert 'entire accepted bounded window' in e['checkpoint_contract']['advance']
    assert 'cannot guarantee' in e['checkpoint_contract']['lateness']
    assert 'date_kind' in e['checkpoint_contract']['identity_fields']


def test_rehearsal_truth_is_explicit_and_ledger_deterministic():
    e=ledger();assert e['source_code_provenance']['rehearsal']=='SYNTHETIC_FAKE_PAGE_NOT_PORTAL_TRUTH'
    assert e['preserved_prs']==[49,50]
    assert json.loads(json.dumps(e,sort_keys=True,separators=(',',':')))==e
