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
# The rebuilding code lives in the production module that the owner's pre-authority verification also uses, so the test and the run can never disagree.
from verification.ingestion_storage.retained_world import (ARCHIVE_DIR, BINDINGS, CAPTURE_CHECKPOINT, CAPTURE_KEY, CON, EVIDENCE as E, MANIFEST, PINS, ROOT_LIMITS, SCOPE, identities, item, retained)      # noqa: E402,F401


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
