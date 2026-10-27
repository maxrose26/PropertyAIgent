"""Integrated proof that the owner-side preparation and the production chain caller carry both families end to end through restricted disposable roles.

The chains themselves are exercised in `test_e2e_connection_pg.py` (which now runs through the same production preparation and caller). This module adds what the connection of the
owner/runner tooling needs on top: genuine outer-supervisor evidence reaching the capture, limit refusal before any source work, and missing, foreign, expired and insufficient authority
against the PREPARED grants. Local fixtures and a disposable database only; the insertion of a prepared registration is a disposable stand-in (the live exception function accepts only the pinned Bolton scope).
"""
import hashlib
import json
import time

import pytest
from sqlalchemy.exc import DBAPIError

from app.ingestion.ledger import Denied, digest
from tests.e2e_chain_caller import Chain, restricted_sessions
from tests.e2e_connection_support import entry, SCHEME
from verification.ingestion_storage.operational_publication import canonical
from tests.e2e_pg_world import disposable_world

FAMILIES = ['idox', 'arcus']


@pytest.fixture(scope='module')
def world():
    yield from disposable_world()


def closed(world, chain):
    assert all(s['cleanup'] == 'CLOSED' and s['connections_closed'] is True for s in chain.accounting.values() if isinstance(s, dict) and 'cleanup' in s)
    deadline = time.monotonic() + 5      # the client has closed; the server reaps the backend asynchronously, so confirm it positively within a short bound
    while restricted_sessions(world['boot']) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert restricted_sessions(world['boot']) == 0


@pytest.mark.parametrize('family', FAMILIES)
def test_the_capture_consumes_the_outer_object_a_real_supervisor_produced(world, tmp_path, family):
    chain = Chain(world, tmp_path, family, 'outer-' + family).owner_reset().owner_registers_capture()
    receipt = chain.capture()
    source, outer = chain.source, chain.outer
    assert source == chain.audit and receipt['source_sha256'] == digest(chain.audit)
    if family == 'arcus':      # the release's own Source.run, under the V2 execution budget, with its cgroup readback
        assert outer['evidence'] == 'SOURCE_CGROUP_READBACK' and outer['cleanup'] == 'CLOSED' and chain.slot_receipt['outer_supervisor'] == outer
        assert chain.slot_receipt['source_sha256'] == hashlib.sha256(canonical(chain.audit)).hexdigest()      # the release's own serialiser and hash
    else:      # the owned-process envelope, which already reported accounting_complete and process counts
        assert outer['accounting_complete'] is True and outer['processes_seen'] >= 1 and outer['cleanup'] == 'CLOSED'
    assert outer['exit_code'] == 0 and outer['live_owned_survivors'] == 0 and outer['limit_hit'] is None
    closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('damage', [dict(live_owned_survivors=1), dict(cleanup='UNKNOWN'), dict(exit_code=1), dict(expired=True), dict(limit_hit='DEADLINE'), dict(peak_owned_rss=None)])
def test_an_outer_object_that_is_not_a_clean_observed_close_stores_nothing(world, tmp_path, family, damage):
    chain = Chain(world, tmp_path, family, 'badouter-' + family).owner_reset().owner_registers_capture()
    chain.supervised_source()
    chain.outer = dict(chain.outer, **damage)
    with pytest.raises(Denied, match='OUTER_SAFETY'):
        chain.capture()
    row = world['boot'].execute('SELECT state, checkpoint FROM ingestion_work_items WHERE key=%s', (chain.root['key'],)).fetchone()
    assert row[1] is None and row[0] != 'COMPLETE' and chain.publisher.calls == []
    closed(world, chain)


def test_an_incompatible_root_is_refused_by_preflight_before_any_source_work(world, tmp_path):
    """A root registered (or later altered) with ledger limits the V2 budget does not fit is refused by the caller's preflight; the source is never run and nothing is archived."""
    chain = Chain(world, tmp_path, 'arcus', 'preflight').owner_reset().owner_registers_capture()
    world['boot'].execute('UPDATE ingestion_work_items SET limits=%s::json WHERE key=%s', (json.dumps(dict(chain.root['limits'], worker_seconds=45, outer_seconds=60)), chain.root['key']))
    with pytest.raises(Denied, match='LIMIT_INCOMPATIBLE:ledger.worker_seconds,ledger.outer_seconds'):
        chain.caller.preflight(chain.root['key'])
    assert chain.source is None and chain.publisher.calls == []      # no supervised source, no archive
    assert world['boot'].execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s', (chain.root['key'],)).fetchone()[0] is None
    closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
def test_a_compatible_root_passes_preflight_and_reports_each_layer(world, tmp_path, family):
    chain = Chain(world, tmp_path, family, 'preflight-ok-' + family).owner_reset().owner_registers_capture()
    layers = chain.caller.preflight(chain.root['key'])
    assert set(layers) == {'reader', 'supervisor', 'ledger', 'grant'} and layers['ledger']['worker_seconds'] == chain.item_limits['worker_seconds']
    closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
def test_missing_authority_stops_the_capture(world, tmp_path, family):
    chain = Chain(world, tmp_path, family, 'missing-' + family).owner_reset().owner_registers_capture()
    control = chain._control()
    del control['grants'][chain.auth_capture]
    chain._write_control(control)
    with pytest.raises(DBAPIError):
        chain.capture()
    assert world['boot'].execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s', (chain.root['key'],)).fetchone()[0] is None and chain.publisher.calls == []
    closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
def test_missing_chain_authority_stops_screening_and_admission(world, tmp_path, family):
    chain = Chain(world, tmp_path, family, 'missing-chain-' + family).owner_reset().owner_registers_capture()
    chain.capture(), chain.read_capture()
    nominees = chain.nominees()
    chain.owner_registers_chain(nominees.nominees)
    control = chain._control()
    del control['grants'][chain.auth_chain]
    chain._write_control(control)
    with pytest.raises(DBAPIError):
        chain.screen()
    assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0] == 0
    closed(world, chain)


def test_an_authority_prepared_for_another_council_cannot_run_this_council(world, tmp_path):
    """The Arcus (Manchester) capture authority is registered and valid; the Idox (Tameside) caller presented with it cannot claim its own root, and vice versa."""
    idox = Chain(world, tmp_path, 'idox', 'foreign-idox').owner_reset().owner_registers_capture()
    arcus = Chain(world, tmp_path, 'arcus', 'foreign-arcus').owner_registers_capture()
    assert idox.auth_capture != arcus.auth_capture
    idox.caller.capture_authority = arcus.auth_capture
    with pytest.raises(DBAPIError):
        idox.capture()
    arcus.caller.capture_authority = idox.auth_capture
    with pytest.raises(DBAPIError):
        arcus.capture()
    for chain in (idox, arcus):
        assert world['boot'].execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s', (chain.root['key'],)).fetchone()[0] is None
    assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0] == 0
    closed(world, idox), closed(world, arcus)


@pytest.mark.parametrize('family', FAMILIES)
def test_a_prepared_chain_grant_covers_exactly_its_own_items(world, tmp_path, family):
    """The chain authority prepared for one capture does not extend to a second capture of the same council: claiming that capture's batch under it is refused."""
    first = Chain(world, tmp_path, family, 'cover-a-' + family).owner_reset().owner_registers_capture()
    first.capture(), first.read_capture()
    nominees = first.nominees()
    first.owner_registers_chain(nominees.nominees)
    second = Chain(world, tmp_path, family, 'cover-b-' + family, [entry('E2E/1/26', SCHEME)]).owner_registers_capture()
    second.capture(), second.read_capture()
    second.owner_registers_chain(second.nominees().nominees)
    second.caller.chain_authority = first.auth_chain      # the first capture's authority, offered for the second capture's items
    with pytest.raises(DBAPIError):
        second.screen()
    assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0] == 0
    closed(world, first), closed(world, second)


@pytest.mark.parametrize('family', FAMILIES)
def test_an_expired_authority_is_refused_at_preparation_and_by_the_database(world, tmp_path, family):
    chain = Chain(world, tmp_path, family, 'expiry-' + family).owner_reset().owner_registers_capture()
    chain.capture(), chain.read_capture()
    nominees = chain.nominees()
    with pytest.raises(Denied, match='grant.lifetime_seconds'):
        chain.owner_registers_chain(nominees.nominees, ttl=-5)      # the owner's preparation refuses: nothing is registered
    assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items WHERE task IN ('LISTING_METADATA','FACTUAL_REFRESH')").fetchone()[0] == 0
    chain.owner_registers_chain(nominees.nominees)      # prepared validly, then it lapses: the database refuses the use
    chain.owner_expires(chain.auth_chain)
    with pytest.raises(DBAPIError):
        chain.screen()
    closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('lower', ['writes', 'source_calls'])
def test_a_prepared_grant_made_insufficient_is_refused_by_the_database(world, tmp_path, family, lower):
    """The preparation derives exact counters (writes = 2 per nominee, source calls = 1); a grant forged below them is refused when the effect needs the missing allowance."""
    boot = world['boot']
    chain = Chain(world, tmp_path, family, f'short-{lower}-{family}').owner_reset().owner_registers_capture()
    chain.capture(), chain.read_capture()
    nominees = chain.nominees()
    chain.owner_registers_chain(nominees.nominees, **({'writes': 1} if lower == 'writes' else {'source_calls': 0}))
    chain.screen()
    adm = chain.prepare(nominees.nominees[0])
    with pytest.raises((DBAPIError, Denied)):
        chain.admit(adm)
    assert boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 0
    closed(world, chain)
    exact = chain.chain_registration.grant
    assert exact['writes'] == 2 * len(nominees.nominees) and exact['source_calls'] == len(nominees.nominees)


@pytest.mark.parametrize('family', FAMILIES)
def test_capture_is_refused_without_a_preflight_of_this_exact_root(world, tmp_path, family):
    chain = Chain(world, tmp_path, family, 'nopreflight-' + family).owner_reset().owner_registers_capture()
    supervised, outer = chain.supervised_source()
    with pytest.raises(Denied, match='PREFLIGHT_REQUIRED'):
        chain.caller.capture(supervised, outer, expected_source_sha256=digest(supervised), evidence_label='TEST_ARCHIVE_NOT_LIVE_EVIDENCE', archive=chain.publisher)
    assert world['boot'].execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s', (chain.root['key'],)).fetchone()[0] is None and chain.publisher.calls == []
    chain.caller.preflighted = 'f' * 64      # a preflight of some OTHER root does not count
    chain.caller.root_key = chain.root['key']
    with pytest.raises(Denied, match='PREFLIGHT_REQUIRED'):
        chain.caller.capture(supervised, outer, expected_source_sha256=digest(supervised), evidence_label='TEST_ARCHIVE_NOT_LIVE_EVIDENCE', archive=chain.publisher)
    closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
def test_only_registered_nominees_can_be_prepared_for_admission(world, tmp_path, family):
    chain = Chain(world, tmp_path, family, 'unregistered-' + family).owner_reset().owner_registers_capture()
    chain.capture(), chain.read_capture()
    nominees = chain.nominees()
    chain.owner_registers_chain(nominees.nominees)
    stray = nominees.nominees[0].__class__(**{**nominees.nominees[0].__dict__, 'reference': 'E2E/3/26'})
    with pytest.raises(Denied, match='CHAIN_NOMINEE_NOT_REGISTERED'):
        chain.caller.prepare(stray)
    closed(world, chain)


@pytest.mark.parametrize('seconds,rss,accepted', [
    (46, 100000, True), (5, 1024**3 + 1, True),
    (75, 1536 * 1024**2, True),
    (75.001, 100000, False), (5, 1536 * 1024**2 + 1, False),
])
def test_selected_v2_boundaries_through_actual_restricted_caller_capture(world, tmp_path, seconds, rss, accepted):
    # Synthetic accounting only: no memory pressure and no delayed source.
    chain = Chain(world, tmp_path, 'arcus', f'v2-bound-{seconds}-{rss}').owner_reset().owner_registers_capture()
    layers = chain.caller.preflight(chain.root['key'])
    assert layers['reader']['worker_seconds'] == layers['ledger']['worker_seconds'] == 75
    assert layers['reader']['rss_ceiling_bytes'] == layers['ledger']['source_rss'] == 1536 * 1024**2
    chain.audit.update(supervisor_seconds=seconds, peak_owned_rss=rss)
    if accepted:
        receipt = chain.capture()
        assert receipt['resources']['supervisor_seconds'] == seconds
        assert receipt['resources']['peak_owned_rss'] == rss
        assert chain.read_capture() == receipt
    else:
        with pytest.raises(Denied, match='SOURCE_SAFETY'):
            chain.capture()
        row = world['boot'].execute('SELECT state, checkpoint FROM ingestion_work_items WHERE key=%s', (chain.root['key'],)).fetchone()
        assert row[1] is None and row[0] != 'COMPLETE'
    closed(world, chain)


@pytest.mark.parametrize('seconds,rss,accepted', [
    (45, 1024**3, True), (45.001, 100000, False), (5, 1024**3 + 1, False),
])
def test_historical_arcus_contract_retains_its_bounds_in_restricted_capture(world, tmp_path, seconds, rss, accepted):
    # No historical Arcus binding is added to the closed ChainCaller registry.
    # Exercise the existing retained-capture entrypoint with a default contract,
    # using the real restricted ledger, archive and committed checkpoint.
    from tests.e2e_connection_support import arcus_audit, arcus_contract, outer
    from tests.e2e_chain_caller import START, END
    chain = Chain(world, tmp_path, 'arcus', f'historical-{seconds}-{rss}').owner_reset().owner_registers_capture()
    historical = arcus_contract('manchester', START, END, name=chain.contract.name)
    source = arcus_audit('manchester', chain.entries, START, END)
    source.update(supervisor_seconds=seconds, peak_owned_rss=rss)
    budget = chain.caller._budget()
    co = chain.caller._coordinator(budget, chain.auth_capture, {historical.name: historical})
    try:
        claim = co.ledger.claim(chain.root['key'], lease_seconds=165)
        def capture():
            return co.retained_capture(claim, source, outer(), chain.publisher,
                expected_source_sha256=digest(source), evidence_label='TEST_ARCHIVE_NOT_LIVE_EVIDENCE')
        if accepted:
            receipt = capture()
            assert co.ledger.get(claim.key)['checkpoint'] == receipt
        else:
            with pytest.raises(Denied, match='ARCUS_AUDIT_REJECTED|SOURCE_RSS'):
                capture()
            assert co.ledger.get(claim.key)['checkpoint'] is None and chain.publisher.calls == []
    finally:
        chain.accounting['historical-capture'] = budget.close([])
    closed(world, chain)
