"""Integrated proof that an owner-accepted single-page window travels the ACTUAL chain with its basis intact, through restricted disposable PostgreSQL roles (specification 037).

The data are synthetic and every acceptance here is TEST-ONLY (labelled, installed by the test that asks for it; the closed production registry is untouched). Archives are labelled test artefacts. A valid zero-nominee outcome is
exercised as such, and is not replaced to demonstrate admission; the eligible synthetic case is separate and labelled. No council, GitHub or production database is contacted.
"""
import json

import pytest

from app.ingestion.ledger import Denied, digest
from app.pipeline.discovery_contract import Completeness, completed_through
from tests.e2e_chain_caller import START, END, Chain, application, restricted_sessions, snapshot
from tests.e2e_connection_support import ASSESS, EXTENSION, LABEL, NO_COUNT, SCHEME, TEST_ACCEPTANCE_KEY, entry, idox_audit, install_test_acceptance, make_test_acceptance
from tests.e2e_pg_world import disposable_world
from tests.test_e2e_connection_pg import FORBIDDEN, assert_closed, unexpected

BASIS = 'OWNER_ACCEPTED_SINGLE_PAGE'
INELIGIBLE = [entry('OWN/1/26', EXTENSION), entry('OWN/2/26', NO_COUNT), entry('OWN/3/26', EXTENSION, address='')]
ELIGIBLE = [entry('OWN/1/26', SCHEME), entry('OWN/2/26', ASSESS), entry('OWN/3/26', EXTENSION)]


@pytest.fixture(scope='module')
def world():
    yield from disposable_world()


def single(entries):
    return idox_audit('oldham', entries, START, END, single_page_no_pager=True)


def chain_for(world, tmp_path, monkeypatch, tag, entries, *, accept=True):
    audit = single(entries)
    acc = install_test_acceptance(monkeypatch, make_test_acceptance(audit, 'oldham', START, END)) if accept else None
    chain = Chain(world, tmp_path, 'idox', tag, council='oldham', audit=audit, owner_acceptance=acc.key if acc else None).owner_reset().owner_registers_capture()
    return chain, acc, audit


def stored_root(world, chain):
    return world['boot'].execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s', (chain.root['key'],)).fetchone()[0]


def test_default_off_a_single_page_total_unknown_capture_is_refused_and_nothing_is_stored(world, tmp_path, monkeypatch):
    chain, _, _ = chain_for(world, tmp_path, monkeypatch, 'own-default', INELIGIBLE, accept=False)
    with pytest.raises(Denied, match='IDOX_WINDOW_BINDING_OR_COMPLETENESS'):
        chain.capture()
    assert stored_root(world, chain) is None and chain.publisher.calls == []      # never archived, never checkpointed
    assert_closed(world, chain)


def test_a_valid_zero_nominee_owner_accepted_window_travels_archive_batching_nomination_and_screening_with_its_basis(world, tmp_path, monkeypatch):
    boot = world['boot']
    chain, acc, audit = chain_for(world, tmp_path, monkeypatch, 'own-zero', INELIGIBLE)
    chain.capture()
    saved = chain.read_capture()
    # archive: the receipt, as the restricted ledger holds it, names the basis and the exact acceptance; the ARCHIVED audit is the immutable original (terminal null, TOTAL_UNKNOWN, UNKNOWN)
    assert saved['completeness_basis'] == BASIS and saved['owner_acceptance'] == acc.binding() and saved['durable_archive']['readback_verified'] is True
    assert saved['segments'] == audit['pages'] and saved['segments'][0]['terminal'] is None and saved['evidence_label'] == LABEL
    archive_file = chain.tmp.parent / (saved['durable_archive']['sha256'] + '.json')      # the isolated test publisher's root is the test directory
    assert archive_file.exists()
    archived = json.loads(archive_file.read_bytes())
    assert archived['enumeration_evidence'] == 'TOTAL_UNKNOWN' and archived['completeness'] == 'UNKNOWN' and 'completeness_basis' not in archived and digest(archived) == acc.data['source']['audit_sha256']
    # nomination: the basis is carried and sealed; the frozen rule decides eligibility, and here there is validly nobody
    nominees = chain.nominees()
    assert nominees.nominees == () and nominees.completeness_bases == (('oldham', digest(saved), BASIS, acc.sha256),) and len(nominees.retained) == 3
    # batching: the batch plan is bound to the capture digest, which covers the basis
    chain.owner_registers_chain(())
    chain.screen()
    assert chain.accounting['screening']
    for batch in chain.batches:
        stored = boot.execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s', (batch['key'],)).fetchone()[0]
        assert stored['plan']['capture_sha256'] == digest(saved) and stored['kind'] == 'BATCH_PROGRESS_V1'
    assert {ref: chain.screening_outcome(ref) for ref in ('OWN/1/26', 'OWN/2/26', 'OWN/3/26')} == {'OWN/1/26': 'RETAIN_NOT_RESIDENTIAL_SUPPLY', 'OWN/2/26': 'ROUTE_COUNT_UNCONFIRMED', 'OWN/3/26': 'RETAIN_NOT_RESIDENTIAL_SUPPLY'}
    # no identity, Site, document or other write came from acceptance or screening
    assert boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 0 and boot.execute('SELECT count(*) FROM sites').fetchone()[0] == 0
    assert_closed(world, chain)
    # coverage never advances
    window = chain.contract.admission_window(saved, 'oldham')
    assert window.outcome == Completeness.COMPLETE and window.completeness_basis == BASIS and completed_through(START - __import__('datetime').timedelta(days=1), [window], council='oldham', date_semantics='RECEIVED') == START - __import__('datetime').timedelta(days=1)


def test_an_eligible_synthetic_owner_accepted_record_set_reaches_committed_readback_with_the_basis_in_the_result(world, tmp_path, monkeypatch):
    boot = world['boot']
    chain, acc, _ = chain_for(world, tmp_path, monkeypatch, 'own-eligible', ELIGIBLE)
    chain.capture(), chain.read_capture()
    nominees = chain.nominees()
    assert [n.reference for n in nominees.nominees] == ['OWN/1/26', 'OWN/2/26'] and nominees.completeness_bases
    chain.owner_registers_chain(nominees.nominees)
    chain.screen()
    before = snapshot(boot)
    for nominee in nominees.nominees:
        adm = chain.prepare(nominee)
        result = chain.admit(adm)
        assert result['outcome'] == 'SUPPORTED_FACTS_VERIFIED' and result['admission'] == 'COMMITTED_PENDING_IDENTITY'
        assert result['enumeration'] == BASIS + '_METADATA_RETAINED' and result['completeness_basis'] == BASIS and result['owner_acceptance'] == acc.binding()      # never reported as a source-complete enumeration
        assert len(adm.detail_calls) == 1
    assert application(boot, 'oldham', 'OWN/3/26') is None and boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 2
    after = snapshot(boot)
    changed = {n for n in before if before[n] != after[n]}
    assert changed <= {'applications', 'application_lifecycle_events'} and not changed & set(FORBIDDEN)      # write confinement
    assert_closed(world, chain)


@pytest.mark.parametrize('forgery', ['strip_basis', 'source_terminal_basis', 'other_acceptance_hash', 'other_key'])
def test_forging_the_stored_basis_is_refused_before_any_detail_call_or_write(world, tmp_path, monkeypatch, forgery):
    boot = world['boot']
    chain, acc, _ = chain_for(world, tmp_path, monkeypatch, 'own-forge-' + forgery, ELIGIBLE)
    chain.capture(), chain.read_capture()
    nominees = chain.nominees()
    chain.owner_registers_chain(nominees.nominees)
    chain.screen()
    adm = chain.prepare(nominees.nominees[0])
    root = chain.root['key']
    if forgery == 'strip_basis':
        boot.execute("UPDATE ingestion_work_items SET checkpoint=(checkpoint::jsonb - 'completeness_basis' - 'owner_acceptance')::json WHERE key=%s", (root,))
    elif forgery == 'source_terminal_basis':
        chain.tamper(root, ['completeness_basis'], 'SOURCE_TERMINAL')
    elif forgery == 'other_acceptance_hash':
        chain.tamper(root, ['owner_acceptance', 'sha256'], '0' * 64)
    else:
        chain.tamper(root, ['owner_acceptance', 'key'], 'INVENTED')
    with pytest.raises(Denied) as exc:
        chain.admit(adm)
    unexpected(exc.value)
    assert adm.detail_calls == [] and boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 0
    assert_closed(world, chain)


def test_an_acceptance_that_does_not_match_the_captured_audit_stores_nothing(world, tmp_path, monkeypatch):
    chain, _, audit = chain_for(world, tmp_path, monkeypatch, 'own-mismatch', INELIGIBLE)
    other = single([entry('OWN/9/26', EXTENSION)])
    install_test_acceptance(monkeypatch, make_test_acceptance(other, 'oldham', START, END))      # the only acceptance the registry holds is for a DIFFERENT audit
    with pytest.raises(Denied, match='OWNER_ACCEPTANCE_SOURCE_DIGEST'):
        chain.capture()
    assert stored_root(world, chain) is None and chain.publisher.calls == []
    assert_closed(world, chain)
