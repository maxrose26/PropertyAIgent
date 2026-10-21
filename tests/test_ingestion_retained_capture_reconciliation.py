"""The verified full retained Bolton capture (RECEIVED 2026-09-28 to 2026-10-04, 24 records), reconciled offline.

The evidence files are byte-for-byte copies of the committed owner evidence (branch stage4/narrow-continuation-evidence-20261016) at their pinned hashes; `.gitattributes` marks them `-text` so no checkout converts them.
This test reproduces every digest with the repository's own generating code and representation. It makes no database, network or council contact."""
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from app.ingestion import listing_screening as ls
from app.ingestion.batching import batch_plans
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.ledger import DEFAULT_LIMITS, digest
from verification.discovery.idox_window import WindowConfig

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / 'tests/fixtures/retained_bolton_window'
ARCHIVE_DIR = 'docs/design/ingestion-operational-execution-bolton-window-demonstration-20261023/'      # the path recorded INSIDE the archive receipt (an identifier, not a location in this repository)
PINS = {'capture/source.json': ('5525be5a6b5fc3fdfac43849bc502cd05c0c9023da1440627b975672fe55013a', 20733),
        'capture-retained/retained.json': ('a47122d0bf386a83f423d0f41d0fb2984a4f3eb8d2cf7cf0aeff74016d7ec2ee', 574),
        'screening-authority/registered.json': ('458c50efd3c55e2ef10193f4449e85ddcb84e2b7eda397eb9bb872fdeedb7c5d', 630),
        'completed/final-result.json': ('d38db9b67dbc8715e9257d040d7dff19c2b759ca6b25393169388d310437ab9e', 15845),
        'completed/events.jsonl': ('26d6392b5f91ce49baa11f45f49dd36371a7e0cdefa837cfadb3aa5b23de2dd0', 44650)}
CAPTURE_CHECKPOINT = 'd5fa9e29bdd51afbf36772e9b08880af6811a8cec771a3335bad0095801445ee'
CAPTURE_KEY = 'd1ff23c04af746a5219e7c109255db0310d2a006c732bcac4f66f126b0240545'
BINDINGS = 'ad4e598267d2104a6d2e0d2321087d84ac6313270f58a2411b3100e66762445f'
CON = 'bolton-received-idox-coordinator-v1'
MANIFEST = '8fb79d78db499a4f5f622ae20debba6397451f242ae0028514246d3234358e0c'
SCOPE = dict(kind='DISCOVERY_SCOPE', council='bolton', start='2026-09-28', end='2026-10-04', semantics='RECEIVED')
ROOT_LIMITS = dict(DEFAULT_LIMITS, requests=10, bytes=3000000, rows=60, pages=6)


def item(identity, *, dependencies=(), checkpoint=None, limits=None, max_attempts=2):      # == verification.ingestion_storage.operational_owner.item (that module imports the Linux-only `resource` module)
    return dict(identity, key=digest(identity), dependencies=list(dependencies), priority=50, eligible_at=0, state='QUEUED', reason=None, next_action='CLAIM_WHEN_AUTHORISED',
                limits=limits or DEFAULT_LIMITS, authority=None, attempt_count=0, max_attempts=max_attempts, fence=0, owner=None, lease_until=None, phase='IDLE', checkpoint=checkpoint, outcome=None)


def retained():
    """(source, receipt) rebuilt exactly as the production run built them. Also used by the controller and PostgreSQL tests."""
    raw = (E / 'capture/source.json').read_bytes()
    source = json.loads(raw)
    events = [json.loads(line) for line in (E / 'completed/events.jsonl').read_bytes().decode('utf-8').splitlines() if line.strip()]
    outer = next(e for e in events if e['event'] == 'source_supervisor_observed')['payload']['actual']
    contract = IdoxListingContract(CON, WindowConfig('bolton', 'RECEIVED', date(2026, 9, 28), date(2026, 10, 4), 0), '1833eb7349dda9b1dceb0924abd7380b2f24e591e13ad34ec37dd8e4763df3f2')
    receipt = contract.project(source, outer, ROOT_LIMITS, source_bytes_limit=512 * 1024)
    receipt.pop('window')
    receipt['durable_archive'] = dict(commit='3587e2778720f56a9510b33c7bbce7584f6be59d', path=ARCHIVE_DIR + 'capture/source.json', sha256=digest(source), bytes=len(raw), readback_verified=True)
    return source, receipt


def identities(receipt):
    """(root, children, plans, batches, bindings) of the registered v1 screening, exactly as the owner registered them."""
    root = item(dict(subject=SCOPE, task='DISCOVERY', contract=CON, revision=MANIFEST), max_attempts=1, limits=ROOT_LIMITS)
    children = [item(dict(subject=dict(kind='APPLICATION', council='bolton', reference=r['reference']), task='SCREENING', contract='listing-screen-v1', revision=digest(r)), dependencies=[root['key']]) for r in receipt['records']]
    plans = batch_plans(root['key'], receipt)
    batches = [item({k: p[k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=p['dependencies'], checkpoint=p['checkpoint']) for p in plans]
    bindings = {x['key']: {k: x[k] for k in ('subject', 'task', 'contract', 'revision')} for x in [*batches, item(dict(subject=SCOPE, task='DISCOVERY', contract=CON, revision=MANIFEST)), *children]}
    return root, children, plans, batches, bindings


@pytest.mark.parametrize('name', sorted(PINS))
def test_each_evidence_copy_is_byte_for_byte_at_its_pinned_hash(name):
    raw = (E / name).read_bytes()
    assert (hashlib.sha256(raw).hexdigest(), len(raw)) == PINS[name]


def test_the_archive_file_is_the_canonical_source_and_the_checkpoint_digest_reproduces_exactly():
    source, receipt = retained()
    raw = (E / 'capture/source.json').read_bytes()
    marker = json.loads((E / 'capture-retained/retained.json').read_bytes())
    assert raw == json.dumps(source, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()      # what archive_capture wrote
    assert hashlib.sha256(raw).hexdigest() == digest(source) == marker['archive_sha256']
    assert digest(receipt) == CAPTURE_CHECKPOINT == marker['capture_sha256']      # a different object derived from the file, so a different hash
    assert receipt['source_sha256'] == digest(source) and receipt['kind'] == 'LISTING_RECEIPT_V1' and len(receipt['records']) == 24


def test_capture_key_child_identities_batches_and_registered_bindings_all_reproduce():
    source, receipt = retained()
    registered = json.loads((E / 'screening-authority/registered.json').read_bytes())
    assert registered['execution']['manifest_sha256'] == MANIFEST
    root, children, plans, batches, bindings = identities(receipt)
    assert root['key'] == CAPTURE_KEY == json.loads((E / 'capture-retained/retained.json').read_bytes())['execution']['capture_key']
    assert len(plans) == 5 and len(children) == 24 and len(bindings) == 30
    assert digest(bindings) == BINDINGS == registered['bindings_sha256']
    recorded = json.loads((E / 'reconciliation.json').read_bytes())
    assert [(r['reference'], r['record_digest'], r['v1_child_key'], r['v1_child_revision']) for r in recorded['records']] == [(c['subject']['reference'], c['revision'], c['key'], c['revision']) for c in children]
    assert [(b['key'], b['revision']) for b in recorded['batches']] == [(b['key'], b['revision']) for b in batches]
    assert all(c['revision'] == digest(r) for c, r in zip(children, receipt['records']))      # a v1 child's revision IS the record digest


def test_the_recorded_v1_aggregate_and_the_projection_fixture_agree_with_the_full_retained_records():
    _, receipt = retained()
    v1 = Counter(ls.screen_row(r)['disposition'] for r in receipt['records'])
    provenance = json.loads((ROOT / 'tests/fixtures/bolton_window_24_listing.PROVENANCE.json').read_bytes())['recorded_v1_aggregate']
    assert v1 == Counter({k: provenance[k] for k in ('INSUFFICIENT_EVIDENCE', 'RELATED_APPLICATION_FOLLOW_THROUGH', 'SUPPORTED_PROCESSING_PRIORITY')})
    projection = json.loads((ROOT / 'tests/fixtures/bolton_window_24_listing.json').read_bytes().replace(b'\r\n', b'\n'))
    assert [(r['reference'], r['fields']['proposal']['value'], r['fields']['address']['value']) for r in receipt['records']] == [(p['reference'], p['proposal'], p['address']) for p in projection]
    v3 = Counter(ls.routing_of(ls.screen_row(r, rule_version=ls.RULE_V3, unit_threshold=10))[1] for r in receipt['records'])
    assert v3 == Counter(RETAIN_NOT_RESIDENTIAL_SUPPLY=16, ROUTE_COUNT_UNCONFIRMED=4, RETAIN_RELATED_TO_PARENT=2, ADMIT_SCHEME=1, RETAIN_BELOW_THRESHOLD=1)      # a LOCAL recomputation, not a production result
