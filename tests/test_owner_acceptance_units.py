"""Offline proof for the owner-accepted single-page window (specification 037). No database, network or council. Synthetic fixtures only; every synthetic acceptance is TEST-ONLY, labelled, and installed solely by the test that
asks for it (the closed production registry is never altered). A passing test here is never admission proof and never qualifies real markup.
"""
import copy
import json
import re
from datetime import date, timedelta
from types import MappingProxyType

import pytest

from app.ingestion import owner_acceptance as oa
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.ledger import DEFAULT_LIMITS, Denied, digest
from app.ingestion.listing_screening import RULE_V3, ScreeningRule
from app.ingestion.nomination import derive_nominees
from app.pipeline.discovery_contract import Completeness, WindowEvidence, completed_through
from tests.e2e_connection_support import (EXTENSION, NO_COUNT, SCHEME, TEST_ACCEPTANCE_KEY, TEST_QUALIFICATION, entry, idox_audit, idox_config, idox_contract, install_test_acceptance, outer,
                                          make_test_acceptance)
from tests.test_e2e_connection_units import END, START

KEY = 'OLDHAM_RECEIVED_20261015_20261021_V1'
PINNED_SHA256 = '3ca962ff74e426f63b0e5b9a173bda52024a152db03423edcfcf60452b136bcf'
SCREENSHOT = 'c57229ec99713bf9c75c35a46180da32d75b60e92eced076cc1a4ffef0287949'
ENTRIES = [entry('E2E/1/26', SCHEME), entry('E2E/2/26', EXTENSION), entry('E2E/3/26', NO_COUNT)]
RULE = ScreeningRule(RULE_V3, unit_threshold=10, link_related=False)


def audit(entries=ENTRIES):
    source = idox_audit('oldham', entries, START, END, single_page_no_pager=True)
    for r in source['records']:
        r.setdefault('processing_screen', dict(retained=True, rule_version='informational'))      # the real audit carries this informational annotation too
    return source


def project(contract, source, **kw):
    return contract.project(source, outer(), DEFAULT_LIMITS, source_bytes_limit=kw.get('limit', 128 * 1024))


def accepted(monkeypatch, source=None, **override):
    source = source if source is not None else audit()
    acc = install_test_acceptance(monkeypatch, make_test_acceptance(source, 'oldham', START, END, **override))
    return acc, idox_contract('oldham', START, END, owner_acceptance=acc.key), source


# -------------------------------------------------------------------------------------------------------------------------------------- the registry
def walk(value, path=()):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from walk(v, path + (k,))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from walk(v, path + (i,))
    else:
        yield path, value


def test_the_registry_is_closed_read_only_pinned_and_holds_exactly_one_entry():
    assert list(oa.ACCEPTANCES) == [KEY] and isinstance(oa.ACCEPTANCES, MappingProxyType)
    with pytest.raises(TypeError):
        oa.ACCEPTANCES['OTHER'] = oa.ACCEPTANCES[KEY]
    assert oa.ACCEPTANCES[KEY].sha256 == PINNED_SHA256      # a change to the entry is a change to this constant: it cannot go unreviewed
    assert not [n for n in dir(oa) if n.lower().startswith(('add', 'register', 'set_', 'create'))]      # nothing adds an entry


def test_the_entry_binds_the_exact_window_evidence_screenshot_and_separate_times():
    d = oa.ACCEPTANCES[KEY].data
    assert (d['council'], d['semantics'], d['start'], d['end'], d['basis']) == ('oldham', 'RECEIVED', '2026-10-15', '2026-10-21', 'OWNER_ACCEPTED_SINGLE_PAGE')
    assert d['manual_review']['screenshot_sha256'] == SCREENSHOT and d['manual_review']['screenshot_bytes'] == 279137
    s = d['source']
    assert s['audit_sha256'] == '97a3fe071da69a7fde32ee7bc663a19d8543c0e49fca5a127415c7e8c7ebc671' and s['enumeration_evidence'] == 'TOTAL_UNKNOWN' and s['record_count'] == 5
    assert s['pages'] == [dict(body_sha256='a9314a7bf1ea0ee9fd512a6d1dec203d92bfd8c77d4e0b4311056be7607596c5', first=None, last=None, ordinal=1, page_size=10, rows=5, terminal=None, total=None)]      # terminal stays null
    c = d['calibration']
    assert c['kind'] == 'DIAGNOSTIC_EVIDENCE_NOT_A_REGISTERED_COLLECTION_AUDIT' and c['classification'] == 'ESTABLISHED' and c['portal_total'] == 16 and c['contained_record_set_sha256'] == s['record_set_sha256']
    t = d['times']
    assert t['owner_decision']['time'] == 'UNKNOWN' and t['manual_review']['timezone'] == 'NOT_STATED' and t['manual_review']['search_criteria_visible'] is False
    assert len(t['source_events_utc']) == 4 and 'observation_time' not in t and 'observed_at' not in t      # separate times; no fabricated common time
    assert 'not a source-stated total' in d['claim'] and d['limits']


def test_the_entry_holds_digests_only_no_record_text_or_address():
    d = oa.ACCEPTANCES[KEY].data
    for path, value in walk(d):
        if path[-1] in ('claim', 'record_set_definition', 'basis', 'note', 'timezone', 'screen_clock', 'time', 'recorded', 'kind', 'classification', 'identity', 'evidence_path', 'evidence_commit', 'code_head', 'code_tree', 'file_name_time',
                        'enumeration_evidence', 'council', 'semantics', 'key', 'date') or not isinstance(value, str):
            continue
        if any(str(p).endswith('sha256') or p == 'file_sha256' for p in path):
            assert re.fullmatch('[0-9a-f]{64}', value), path
    text = oa.ACCEPTANCES[KEY].text
    assert not re.search(r'[A-Z]{2,4}/\d{5,7}/\d{2}', text) and 'Road' not in text and 'storey' not in text and 'extension' not in text


def test_require_accepts_only_a_registry_key_string():
    assert oa.require(KEY) is oa.ACCEPTANCES[KEY]
    for bad in (None, '', 'unknown', KEY + ' ', KEY.lower(), oa.ACCEPTANCES[KEY], oa.ACCEPTANCES[KEY].data, oa.ACCEPTANCES[KEY].sha256, KEY.encode(), [KEY], TEST_ACCEPTANCE_KEY):
        with pytest.raises(Denied, match='OWNER_ACCEPTANCE_UNKNOWN'):
            oa.require(bad)


def test_a_contract_refuses_a_caller_supplied_acceptance_and_a_wrong_scope():
    for bad in (oa.ACCEPTANCES[KEY], oa.ACCEPTANCES[KEY].data, oa.ACCEPTANCES[KEY].sha256, 'invented'):
        with pytest.raises(Denied, match='OWNER_ACCEPTANCE_UNKNOWN'):
            IdoxListingContract('x', idox_config('oldham', date(2026, 10, 15), date(2026, 10, 21)), TEST_QUALIFICATION, owner_acceptance=bad)
    ok = IdoxListingContract('x', idox_config('oldham', date(2026, 10, 15), date(2026, 10, 21)), TEST_QUALIFICATION, owner_acceptance=KEY)
    assert ok.owner_acceptance == KEY
    for council, start, end in (('tameside', date(2026, 10, 15), date(2026, 10, 21)), ('oldham', date(2026, 10, 8), date(2026, 10, 14)), ('oldham', date(2026, 10, 15), date(2026, 10, 20)), ('bury', date(2026, 10, 15), date(2026, 10, 21))):
        with pytest.raises(Denied, match='OWNER_ACCEPTANCE_SCOPE'):
            IdoxListingContract('x', idox_config(council, start, end), TEST_QUALIFICATION, owner_acceptance=KEY)
    with pytest.raises(Denied, match='OWNER_ACCEPTANCE_UNKNOWN'):
        idox_contract('oldham', START, END, owner_acceptance=TEST_ACCEPTANCE_KEY)      # the test key does not exist unless a test installs it


# --------------------------------------------------------------------------------------------------------------- default and source-reconciled paths
def test_default_off_a_total_unknown_source_is_still_refused_and_the_key_is_not_consulted_for_a_counted_source(monkeypatch):
    source = audit()
    assert source['enumeration_evidence'] == 'TOTAL_UNKNOWN' and source['pages'][0]['terminal'] is None
    with pytest.raises(Denied, match='IDOX_WINDOW_BINDING_OR_COMPLETENESS'):
        project(idox_contract('oldham', START, END), source)
    many = [entry('E2E/%d/26' % i, SCHEME) for i in range(1, 13)]
    counted = idox_audit('oldham', many, START, END)
    assert counted['enumeration_evidence'] == 'COUNT_RECONCILED'
    plain = project(idox_contract('oldham', START, END), counted)
    acc = install_test_acceptance(monkeypatch, make_test_acceptance(audit(), 'oldham', START, END))
    keyed = project(idox_contract('oldham', START, END, owner_acceptance=acc.key), counted)
    assert keyed == plain and 'completeness_basis' not in keyed and 'owner_acceptance' not in keyed      # an acceptance is never consulted when the source states a count


def test_a_source_that_carries_a_pager_or_total_never_uses_the_acceptance(monkeypatch):
    two_pages = idox_audit('oldham', [entry('E2E/%d/26' % i, SCHEME) for i in range(1, 12)], START, END)
    acc = install_test_acceptance(monkeypatch, make_test_acceptance(two_pages, 'oldham', START, END))      # even an acceptance built FROM it
    r = project(idox_contract('oldham', START, END, owner_acceptance=acc.key), two_pages)
    assert 'completeness_basis' not in r and r['segments'][-1]['terminal'] == 'EXPLICIT_LAST_EQUALS_TOTAL'


# ----------------------------------------------------------------------------------------------------------------------------------- the accepted path
def test_an_exact_match_projects_a_labelled_receipt_and_leaves_the_audit_and_its_pagination_untouched(monkeypatch):
    acc, contract, source = accepted(monkeypatch)
    before = copy.deepcopy(source)
    receipt = project(contract, source)
    assert source == before and digest(source) == digest(before)      # the original audit is immutable and stays UNKNOWN
    assert receipt['completeness_basis'] == 'OWNER_ACCEPTED_SINGLE_PAGE' and receipt['owner_acceptance'] == acc.binding()
    assert receipt['segments'] == source['pages'] and receipt['segments'][0]['terminal'] is None and receipt['segments'][0]['total'] is None      # the source's own pagination facts, unchanged
    assert receipt['source_sha256'] == digest(source) and len(receipt['records']) == 3 and source['completeness'] == 'UNKNOWN'
    assert all(r['provenance']['body_sha256'] == source['pages'][0]['body_sha256'] for r in receipt['records'])


def test_the_window_proof_is_complete_only_with_the_explicit_basis_and_never_advances_coverage(monkeypatch):
    acc, contract, source = accepted(monkeypatch)
    receipt = project(contract, source)
    w = contract.admission_window(receipt, 'oldham')
    assert w.outcome == Completeness.COMPLETE and w.completeness_basis == 'OWNER_ACCEPTED_SINGLE_PAGE' and w.owner_acceptance_sha256 == acc.sha256 and w.terminal_evidence is None
    before = START - timedelta(days=1)
    assert completed_through(before, [w], council='oldham', date_semantics='RECEIVED') == before      # no coverage advance
    counted = idox_audit('oldham', [entry('E2E/%d/26' % i, SCHEME) for i in range(1, 13)], START, END)
    c = idox_contract('oldham', START, END)
    assert completed_through(before, [c.admission_window(project(c, counted), 'oldham')], council='oldham', date_semantics='RECEIVED') == END      # a source-reconciled window still advances


# ---------------------------------------------------------------------------------------------------------------------------------- refusal matrix
def mutated(mutate):
    source = audit()
    mutate(source)
    return source


@pytest.mark.parametrize('mutate', [
    lambda a: a['resource'].update(requests_attempted=a['resource']['requests_attempted'] + 1),
    lambda a: a['records'][0]['fields']['proposal'].update(value='Erection of 30 residential dwellings'),
    lambda a: a['records'][0]['fields']['address'].update(value='9 Other Street'),
    lambda a: a['records'][0]['fields']['received_date'].update(value='Tue 10 Nov 2026'),
    lambda a: a['records'][0]['fields']['validated_date'].update(state='NOT_PRESENT', value=None),
    lambda a: a['records'][0]['fields']['proposal'].update(locator='other:locator'),
    lambda a: a['records'][0].update(source_url=a['records'][0]['source_url'] + '&x=1'),
    lambda a: a['records'][0].update(source_key='OTHERKEY'),
    lambda a: a['records'][0].update(identity_state='CONFLICTING'),
    lambda a: a['records'].pop(),
    lambda a: a['records'].append(copy.deepcopy(a['records'][0])),
    lambda a: a['records'][0]['processing_screen'].update(retained=False),      # even the informational annotation: the whole audit is bound
    lambda a: a.update(cleanup='UNKNOWN'),
    lambda a: a['pages'][0].update(page_size=20),
], ids=['accounting', 'proposal', 'address', 'received', 'validated-state', 'locator', 'url', 'key', 'identity-state', 'missing-record', 'extra-record', 'annotation', 'cleanup', 'page-size'])
def test_any_change_to_the_bound_audit_refuses_the_acceptance(monkeypatch, mutate):
    acc, contract, source = accepted(monkeypatch)
    source = copy.deepcopy(source)
    mutate(source)
    with pytest.raises(Denied, match='OWNER_ACCEPTANCE_(SOURCE_DIGEST|SOURCE_FACTS|PAGE_FACTS|RECORD_SET)'):
        project(contract, source)


def test_a_swap_of_metadata_between_records_changes_the_joint_record_digest():
    a = audit()
    b = copy.deepcopy(a)
    b['records'][0]['fields'], b['records'][1]['fields'] = b['records'][1]['fields'], b['records'][0]['fields']
    assert oa.record_set_digest(a['records']) != oa.record_set_digest(b['records'])
    c = copy.deepcopy(a)
    c['records'][0]['processing_screen'] = dict(anything=1)
    assert oa.record_set_digest(a['records']) == oa.record_set_digest(c['records'])      # only the informational annotation is excluded
    assert oa.record_set_digest(a['records']) == oa.record_set_digest(list(reversed(a['records'])))      # order-independent


@pytest.mark.parametrize('override,code', [
    (dict(record_set_sha256='0' * 64), 'OWNER_ACCEPTANCE_RECORD_SET'), (dict(record_count=2), 'OWNER_ACCEPTANCE_PAGE_FACTS'), (dict(applied_evidence_sha256='0' * 64), 'OWNER_ACCEPTANCE_SOURCE_FACTS'),
    (dict(enumeration_evidence='COUNT_RECONCILED'), 'OWNER_ACCEPTANCE_SOURCE_FACTS'), (dict(audit_sha256='0' * 64), 'OWNER_ACCEPTANCE_SOURCE_DIGEST')])
def test_each_expected_field_of_the_entry_is_checked_on_its_own(monkeypatch, override, code):
    _, contract, source = accepted(monkeypatch, **override)
    with pytest.raises(Denied, match=code):
        project(contract, source)


def test_the_page_entry_is_checked_and_the_single_page_shape_is_enforced_independently(monkeypatch):
    _, contract, source = accepted(monkeypatch, pages=[dict(audit()['pages'][0], rows=2)])
    with pytest.raises(Denied, match='OWNER_ACCEPTANCE_PAGE_FACTS'):
        project(contract, source)
    for change in (dict(terminal='EXPLICIT_LAST_EQUALS_TOTAL'), dict(total=3), dict(first=1), dict(last=3)):
        shaped = audit()
        shaped['pages'][0].update(change)
        _, contract, _ = accepted(monkeypatch, shaped)      # an acceptance that matches the mutated page exactly still refuses: the shape itself must be single-page, null pagination
        with pytest.raises(Denied, match='OWNER_ACCEPTANCE_PAGE_FACTS'):
            project(contract, shaped)
    two = audit()
    two['pages'].append(dict(two['pages'][0], ordinal=2))
    _, contract, _ = accepted(monkeypatch, two)
    with pytest.raises(Denied, match='OWNER_ACCEPTANCE_PAGE_FACTS'):
        project(contract, two)


@pytest.mark.parametrize('mutate,code', [
    (lambda a: a.update(cleanup='UNKNOWN'), 'IDOX_WINDOW_BINDING_OR_COMPLETENESS'), (lambda a: a.update(failure='X'), 'OWNER_ACCEPTANCE_SOURCE_FACTS'), (lambda a: a.update(capped=True), 'OWNER_ACCEPTANCE_SOURCE_FACTS'),
    (lambda a: a['criteria_result_binding'].update(method='OTHER') if 'criteria_result_binding' in a else a.update(applied_evidence_sha256='bad'), 'IDOX_CRITERIA'),
    (lambda a: a['response_provenance'].pop(), 'IDOX_RESPONSE'), (lambda a: a['resource'].update(requests_attempted=11), 'IDOX_'), (lambda a: a['resource'].update(received_bytes=4_000_000), 'IDOX_RESOURCE_BOUND'),
    (lambda a: a['resource'].update(retries=1), 'IDOX_ACCOUNTING'), (lambda a: a['resource'].update(elapsed_seconds=46), 'IDOX_CLOCK'),
    (lambda a: a['records'][0]['fields']['received_date'].update(value='Mon 02 Nov 2026'), 'IDOX_ROW_DATE'),
], ids=['cleanup', 'failure', 'capped', 'criteria', 'provenance', 'requests', 'bytes', 'retries', 'clock', 'row-date'])
def test_every_other_existing_gate_is_unchanged_even_with_a_matching_acceptance(monkeypatch, mutate, code):
    source = audit()
    mutate(source)
    _, contract, source = accepted(monkeypatch, source)      # the acceptance is rebuilt to match the mutated audit: only the unchanged gates can refuse
    with pytest.raises(Denied, match=code):
        project(contract, source)


def test_the_supervisor_gate_is_unchanged(monkeypatch):
    _, contract, source = accepted(monkeypatch)
    for damage in (dict(exit_code=1), dict(cleanup='UNKNOWN'), dict(live_owned_survivors=1), dict(expired=True), dict(elapsed_seconds=60), dict(peak_owned_rss=None)):
        with pytest.raises(Denied, match='OUTER_SAFETY'):
            contract.project(source, dict(outer(), **damage), DEFAULT_LIMITS, source_bytes_limit=128 * 1024)


# ----------------------------------------------------------------------------------------------------------------------------- receipt forgery at admission
def test_a_receipt_basis_is_revalidated_by_the_contract_at_admission(monkeypatch):
    acc, contract, source = accepted(monkeypatch)
    good = project(contract, source)
    plain = idox_contract('oldham', START, END)
    with pytest.raises(Denied, match='OWNER_ACCEPTANCE_RECEIPT_BINDING'):
        plain.admission_window(good, 'oldham')      # a contract without the acceptance refuses a receipt that claims one
    forgeries = {
        'wrong_binding': lambda r: r.update(owner_acceptance=dict(r['owner_acceptance'], sha256='0' * 64)), 'wrong_key': lambda r: r.update(owner_acceptance=dict(r['owner_acceptance'], key='OTHER')),
        'basis_other': lambda r: r.update(completeness_basis='SOURCE_TERMINAL'), 'basis_without_acceptance': lambda r: r.pop('owner_acceptance'),
        'acceptance_without_basis': lambda r: r.pop('completeness_basis'), 'terminal_set': lambda r: r['segments'][0].update(terminal='EXPLICIT_LAST_EQUALS_TOTAL'),
        'two_segments': lambda r: r['segments'].append(dict(r['segments'][0], ordinal=2)), 'other_source': lambda r: r.update(source_sha256='0' * 64), 'fewer_records': lambda r: r['records'].pop()}
    for name, forge in forgeries.items():
        r = copy.deepcopy(good)
        forge(r)
        with pytest.raises(Denied, match='OWNER_ACCEPTANCE_RECEIPT_BINDING'):
            contract.admission_window(r, 'oldham')
    stripped = copy.deepcopy(good)
    for k in ('completeness_basis', 'owner_acceptance'):
        stripped.pop(k)
    assert contract.admission_window(stripped, 'oldham').outcome != Completeness.COMPLETE      # no basis and no source terminal: never complete


def test_windowevidence_rules_for_the_basis():
    def window(**kw):
        base = dict(council='oldham', run_id='r', requested_start=START, requested_end=END, applied_start=START, applied_end=END, date_semantics='RECEIVED', source_contract='c', applied_evidence='e',
                    terminal_evidence=None, pages=1, unique_references=3, requests=4, observed_bytes=1, elapsed_seconds=1.0)
        base.update(kw)
        return WindowEvidence(**base)
    assert window(terminal_evidence='EXPLICIT_LAST_EQUALS_TOTAL').outcome == Completeness.COMPLETE and window().outcome == Completeness.INCOMPLETE      # default basis unchanged
    owner = window(completeness_basis='OWNER_ACCEPTED_SINGLE_PAGE', owner_acceptance_sha256='a' * 64)
    assert owner.outcome == Completeness.COMPLETE
    for bad in (dict(completeness_basis='OWNER_ACCEPTED_SINGLE_PAGE'), dict(completeness_basis='OWNER_ACCEPTED_SINGLE_PAGE', owner_acceptance_sha256='nothex'),
                dict(completeness_basis='OWNER_ACCEPTED_SINGLE_PAGE', owner_acceptance_sha256='a' * 64, terminal_evidence='EXPLICIT_LAST_EQUALS_TOTAL'),
                dict(completeness_basis='OWNER_ACCEPTED_SINGLE_PAGE', owner_acceptance_sha256='a' * 64, explicit_zero=True, unique_references=0), dict(owner_acceptance_sha256='a' * 64),
                dict(completeness_basis='SOMETHING_ELSE'), dict(completeness_basis='SOURCE_TERMINAL', owner_acceptance_sha256='a' * 64)):
        with pytest.raises(ValueError):
            window(**bad)
    assert window(completeness_basis='OWNER_ACCEPTED_SINGLE_PAGE', owner_acceptance_sha256='a' * 64, unique_references=0).outcome == Completeness.UNKNOWN
    assert window(completeness_basis='OWNER_ACCEPTED_SINGLE_PAGE', owner_acceptance_sha256='a' * 64, capped=True).outcome == Completeness.INCOMPLETE
    assert window(completeness_basis='OWNER_ACCEPTED_SINGLE_PAGE', owner_acceptance_sha256='a' * 64, applied_end=END - timedelta(days=1)).outcome == Completeness.UNKNOWN


# --------------------------------------------------------------------------------------------------------------------------------- nominee sets
def archived(receipt):
    receipt = copy.deepcopy(receipt)
    receipt.pop('window', None)
    receipt['durable_archive'] = dict(label='TEST_ARCHIVE_NOT_LIVE_EVIDENCE')
    receipt['evidence_label'] = 'TEST_ARCHIVE_NOT_LIVE_EVIDENCE'
    return receipt


def test_the_basis_is_carried_and_sealed_in_the_nominee_set_only_when_it_is_owner_accepted(monkeypatch):
    acc, contract, source = accepted(monkeypatch)
    receipt = archived(project(contract, source))
    ns = derive_nominees([receipt], RULE, allow_test_evidence=True)
    assert ns.completeness_bases == (('oldham', digest(receipt), 'OWNER_ACCEPTED_SINGLE_PAGE', acc.sha256),)
    assert [n.reference for n in ns.nominees] == ['E2E/1/26']      # eligibility is decided record by record by the frozen v3 rule, never by the acceptance
    _, ineligible_contract, ineligible_source = accepted(monkeypatch, audit([entry('E2E/2/26', EXTENSION), entry('E2E/3/26', NO_COUNT)]))
    none = derive_nominees([archived(project(ineligible_contract, ineligible_source))], RULE, allow_test_evidence=True)
    assert none.nominees == () and len(none.retained) == 2 and none.completeness_bases      # a valid zero-nominee outcome
    counted = idox_audit('oldham', [entry('E2E/%d/26' % i, SCHEME if i == 1 else EXTENSION) for i in range(1, 13)], START, END)
    plain = archived(project(idox_contract('oldham', START, END), counted))
    plain_set = derive_nominees([plain], RULE, allow_test_evidence=True)
    assert plain_set.completeness_bases == ()
    sealed = dict(configuration=digest(RULE.config()), nominees=[__import__('dataclasses').asdict(n) for n in plain_set.nominees], retained=[list(x) for x in plain_set.retained], conflicts=[])
    assert plain_set.sha256 == digest(sealed)      # a source-terminal receipt's nominee-set digest is exactly what it was before this change
    assert len(ns.sha256) == 64


def test_the_owner_accepted_set_digest_differs_from_a_source_terminal_set_with_the_same_records(monkeypatch):
    acc, contract, source = accepted(monkeypatch)
    receipt = archived(project(contract, source))
    stripped = copy.deepcopy(receipt)
    for k in ('completeness_basis', 'owner_acceptance'):
        stripped.pop(k)
    assert derive_nominees([receipt], RULE, allow_test_evidence=True).sha256 != derive_nominees([stripped], RULE, allow_test_evidence=True).sha256


# ------------------------------------------------------------------------------------------------------------------- review follow-ups
def test_a_default_receipts_window_carries_no_basis_fields_so_its_digest_is_what_it_was(monkeypatch):
    counted = idox_audit('oldham', [entry('E2E/%d/26' % i, SCHEME) for i in range(1, 13)], START, END)
    window = project(idox_contract('oldham', START, END), counted)['window']
    assert 'completeness_basis' not in window and 'owner_acceptance_sha256' not in window
    _, contract, source = accepted(monkeypatch)
    owner_window = project(contract, source)['window']
    assert owner_window['completeness_basis'] == BASIS_NAME and len(owner_window['owner_acceptance_sha256']) == 64


BASIS_NAME = 'OWNER_ACCEPTED_SINGLE_PAGE'


def test_the_observation_history_refuses_to_treat_an_owner_accepted_receipt_as_a_complete_capture(monkeypatch):
    from app.ingestion.observation_history import link_complete_capture
    _, contract, source = accepted(monkeypatch)
    receipt = archived(project(contract, source))
    with pytest.raises(Denied, match='SOURCE_RECONCILED_RECEIPT_REQUIRED'):
        link_complete_capture(dict(applications={}, links=[], conflicts=[]), receipt, observed_at='2026-11-16T00:00:00+00:00')


def test_a_receipt_whose_segments_differ_from_the_entrys_pages_is_refused_at_admission(monkeypatch):
    _, contract, source = accepted(monkeypatch)
    receipt = project(contract, source)
    receipt['segments'][0]['rows'] = 99
    with pytest.raises(Denied, match='OWNER_ACCEPTANCE_RECEIPT_BINDING'):
        contract.admission_window(receipt, 'oldham')
