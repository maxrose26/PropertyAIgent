"""OPT-IN, local only: the PRODUCTION registry entry against the REAL retained Oldham evidence (specification 037). Skipped unless OLDHAM_ACCEPTANCE_EVIDENCE_DIR names an owner-local, private directory holding
`source.json` (the original audit), `slot-receipt.json` (its slot receipt) and, optionally, `owner-screenshot.png`. The evidence is public-register data kept private; it is never committed and never published. The chain runs through the
disposable PostgreSQL world only, with TEST-labelled archives; nothing here contacts a council, GitHub or a production database, and a valid zero-nominee outcome is reported as exactly that.
"""
import hashlib
import json
import os
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.ingestion import owner_acceptance as oa
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.ledger import DEFAULT_LIMITS, Denied, digest
from app.pipeline.discovery_contract import Completeness, completed_through
from tests.e2e_chain_caller import Chain, restricted_sessions, snapshot
from tests.e2e_connection_support import idox_config
from tests.e2e_pg_world import disposable_world
from tests.test_e2e_connection_pg import assert_closed
from verification.discovery.outer_evidence import outer_from_slot_receipt

DIR = os.environ.get('OLDHAM_ACCEPTANCE_EVIDENCE_DIR')
pytestmark = pytest.mark.skipif(not DIR, reason='opt-in: needs the owner-local evidence directory')
KEY = 'OLDHAM_RECEIVED_20261015_20261021_V1'
QUALIFICATION = '3d519c158bb35d50ad7d1472e842e40eb850dcde6ee7a6e01eda36e91589a003'      # the accepted Oldham qualification object's canonical digest
WINDOW = (date(2026, 10, 15), date(2026, 10, 21))


def load():
    d = Path(DIR)
    return json.loads((d / 'source.json').read_bytes()), json.loads((d / 'slot-receipt.json').read_bytes()), d


def test_the_registry_entry_matches_the_real_evidence_files():
    source, receipt, d = load()
    entry = oa.ACCEPTANCES[KEY].data
    assert hashlib.sha256((d / 'source.json').read_bytes()).hexdigest() == digest(source) == entry['source']['audit_sha256']
    assert hashlib.sha256((d / 'slot-receipt.json').read_bytes()).hexdigest() == entry['source']['slot_receipt_sha256']
    if (d / 'owner-screenshot.png').exists():
        assert hashlib.sha256((d / 'owner-screenshot.png').read_bytes()).hexdigest() == entry['manual_review']['screenshot_sha256']
    oa.require(KEY).verify_source(source, idox_config('oldham', *WINDOW))
    assert oa.record_set_digest(source['records']) == entry['source']['record_set_sha256'] and source['completeness'] == 'UNKNOWN' and source['pages'][0]['terminal'] is None


def test_the_real_audit_is_refused_by_default_accepted_with_the_key_and_never_advances_coverage():
    source, receipt, _ = load()
    outer = outer_from_slot_receipt(receipt, source)
    before = json.dumps(source, sort_keys=True)
    with pytest.raises(Denied, match='IDOX_WINDOW_BINDING_OR_COMPLETENESS'):
        IdoxListingContract('oldham-real-check', idox_config('oldham', *WINDOW), QUALIFICATION).project(source, outer, DEFAULT_LIMITS, source_bytes_limit=512 * 1024)
    contract = IdoxListingContract('oldham-real-check', idox_config('oldham', *WINDOW), QUALIFICATION, owner_acceptance=KEY)
    projected = contract.project(source, outer, DEFAULT_LIMITS, source_bytes_limit=512 * 1024)
    assert json.dumps(source, sort_keys=True) == before and projected['completeness_basis'] == 'OWNER_ACCEPTED_SINGLE_PAGE' and projected['segments'][0]['terminal'] is None and len(projected['records']) == 5
    window = contract.admission_window(projected, 'oldham')
    day_before = WINDOW[0] - timedelta(days=1)
    assert window.outcome == Completeness.COMPLETE and completed_through(day_before, [window], council='oldham', date_semantics='RECEIVED') == day_before


@pytest.fixture(scope='module')
def world():
    yield from disposable_world()


def test_the_real_record_set_runs_the_actual_chain_to_a_valid_zero_nominee_outcome_with_its_basis(world, tmp_path):
    source, receipt, _ = load()
    boot = world['boot']
    chain = Chain(world, tmp_path, 'idox', 'real-oldham', council='oldham', audit=source, owner_acceptance=KEY, window=WINDOW, qualification=QUALIFICATION).owner_reset().owner_registers_capture()
    chain.source, chain.outer = source, outer_from_slot_receipt(receipt, source)      # the original audit and its own supervisor evidence, exactly as retained
    saved = chain.capture()
    saved = chain.read_capture()
    assert saved['completeness_basis'] == 'OWNER_ACCEPTED_SINGLE_PAGE' and saved['owner_acceptance'] == oa.require(KEY).binding() and saved['source_sha256'] == digest(source) and saved['segments'][0]['terminal'] is None
    nominees = chain.nominees()
    chain.owner_registers_chain(nominees.nominees)
    chain.screen()
    outcomes = Counter(chain.screening_outcome(r['reference']) for r in saved['records'])
    assert len(saved['records']) == 5 and nominees.nominees == () and nominees.completeness_bases and sum(outcomes.values()) == 5      # whatever the frozen rule decides, validly: here nobody is nominated
    print('REAL RECORD SET OUTCOMES', dict(outcomes))
    assert boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 0 and boot.execute('SELECT count(*) FROM sites').fetchone()[0] == 0
    assert_closed(world, chain)
