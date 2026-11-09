"""PA-D002: offline receipt contract checks; all evidence/SQL stubs disposable."""
import hashlib
import json

import pytest

from app.ingestion.batching import archive_capture
from app.ingestion.ledger import Denied
from app.ingestion.private_evidence import (
    BACKEND, verified_private_capture, require_private_receipt,
)

PERIOD = 'offline-pa-d002'
RUN = 'a' * 32
NAME = 'capture-1/source.json'
SOURCE = {'case': 'synthetic', 'listing_records': [{'reference': 'TEST-ONLY'}]}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def verified_stubs(raw):
    calls = []
    persisted = {}

    def write(body):
        calls.append('write')
        persisted['raw'] = body
        return {'sha256': hashlib.sha256(body).hexdigest(),
                'bytes': len(body), 'readback_verified': False}

    def readback():
        calls.append('read')
        return persisted['raw']

    return write, readback, calls, persisted


def test_verified_private_receipt_requires_actual_exact_source_readback():
    raw = canonical(SOURCE)
    write, read, calls, persisted = verified_stubs(raw)
    receipt = verified_private_capture(raw, period=PERIOD, run_id=RUN, name=NAME,
                                       write=write, readback=read)
    assert calls == ['write', 'read']
    assert receipt == {'backend': BACKEND, 'period': PERIOD, 'run_id': RUN,
                       'name': NAME, 'sha256': hashlib.sha256(raw).hexdigest(),
                       'bytes': len(raw), 'readback_verified': True}
    assert 'listing_records' not in str(receipt)
    assert require_private_receipt(receipt, raw) == receipt


def test_private_receipt_passes_existing_archive_capture_without_fake_git_commit():
    raw = canonical(SOURCE)
    write, read, calls, _ = verified_stubs(raw)
    receipt = archive_capture(
        SOURCE,
        lambda body: verified_private_capture(body, period=PERIOD, run_id=RUN,
                                              name=NAME, write=write, readback=read),
    )
    assert receipt['backend'] == BACKEND
    assert 'commit' not in receipt and 'path' not in receipt
    assert calls == ['write', 'read']


def test_historical_git_receipt_validation_is_unchanged():
    raw = canonical(SOURCE)
    legacy = {'commit': 'b' * 40, 'path': 'docs/design/historical/capture-1/source.json',
              'sha256': hashlib.sha256(raw).hexdigest(),
              'bytes': len(raw), 'readback_verified': True}
    assert archive_capture(SOURCE, lambda _: legacy) == legacy
    for changed in ({**legacy, 'commit': 'x' * 40},
                    {**legacy, 'path': '../sneaky/source.json'},
                    {**legacy, 'readback_verified': False},
                    {**legacy, 'backend': 'GIT_V1'}):
        with pytest.raises(Denied, match='DURABLE_ARCHIVE_NOT_VERIFIED'):
            archive_capture(SOURCE, lambda _: changed)


@pytest.mark.parametrize('name', [
    'capture-3/source.json', 'capture-1/../source.json', 'final/result-before-publication.json',
])
def test_wrong_source_capture_slot_refused_before_write(name):
    raw = canonical(SOURCE)
    write, read, calls, _ = verified_stubs(raw)
    with pytest.raises(Denied, match='PRIVATE_EVIDENCE_SCOPE_BOUND'):
        verified_private_capture(raw, period=PERIOD, run_id=RUN, name=name,
                                 write=write, readback=read)
    assert calls == []


@pytest.mark.parametrize('period,run_id', [
    ('bad/period', RUN), (PERIOD, 'not-a-run'), ('', RUN), (PERIOD, 'a' * 40),
])
def test_invalid_scope_refused_before_write(period, run_id):
    raw = canonical(SOURCE)
    write, read, calls, _ = verified_stubs(raw)
    with pytest.raises(Denied, match='PRIVATE_EVIDENCE_SCOPE_BOUND'):
        verified_private_capture(raw, period=period, run_id=run_id, name=NAME,
                                 write=write, readback=read)
    assert calls == []


def test_oversized_original_never_written_or_truncated():
    raw = b'x' * (524288 + 1)
    write, read, calls, _ = verified_stubs(raw)
    with pytest.raises(Denied, match='PRIVATE_EVIDENCE_SOURCE_BOUND'):
        verified_private_capture(raw, period=PERIOD, run_id=RUN, name=NAME,
                                 write=write, readback=read)
    assert calls == []


@pytest.mark.parametrize('alter', [
    lambda raw: b'wrong',
    lambda raw: raw[:-1] + b'Z',
    lambda raw: None,
])
def test_acknowledged_but_mismatched_or_unavailable_sql_readback_refused(alter):
    raw = canonical(SOURCE)
    write, _, calls, persisted = verified_stubs(raw)
    def stale_read():
        calls.append('read')
        return alter(raw)
    with pytest.raises(Denied, match='PRIVATE_EVIDENCE_READBACK_MISMATCH'):
        verified_private_capture(raw, period=PERIOD, run_id=RUN, name=NAME,
                                 write=write, readback=stale_read)
    assert calls == ['write', 'read']


@pytest.mark.parametrize('tamper', [
    lambda ack: {**ack, 'readback_verified': True},
    lambda ack: {**ack, 'sha256': '0' * 64},
    lambda ack: {**ack, 'bytes': True},
    lambda ack: {**ack, 'bytes': ack['bytes'] + 1},
    lambda ack: None,
])
def test_invalid_sql_write_ack_refused_without_false_verified_receipt(tamper):
    raw = canonical(SOURCE)
    write, read, calls, _ = verified_stubs(raw)
    def bad_write(body):
        return tamper(write(body))
    with pytest.raises(Denied, match='PRIVATE_EVIDENCE_WRITE_ACK_UNVERIFIED'):
        verified_private_capture(raw, period=PERIOD, run_id=RUN, name=NAME,
                                 write=bad_write, readback=read)
    assert calls == ['write']


def test_unknown_or_mixed_backend_receipts_cannot_pass_archive_capture():
    raw = canonical(SOURCE)
    write, read, _, _ = verified_stubs(raw)
    valid = verified_private_capture(raw, period=PERIOD, run_id=RUN, name=NAME,
                                     write=write, readback=read)
    for changed in ({**valid, 'backend': 'UNKNOWN'},
                    {**valid, 'commit': 'a' * 40},
                    {**valid, 'path': 'docs/design/fake'},
                    {**valid, 'readback_verified': False},
                    {**valid, 'sha256': 'f' * 64},
                    {**valid, 'period': 'evil/path'},
                    {**valid, 'run_id': '1'},
                    {**valid, 'name': 'capture-3/source.json'}):
        with pytest.raises(Denied, match='DURABLE_ARCHIVE_NOT_VERIFIED'):
            archive_capture(SOURCE, lambda _: changed)
