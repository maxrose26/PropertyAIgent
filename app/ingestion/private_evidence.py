"""Fail-closed offline private source-archive receipt boundary (PA-D002).

This module does not issue SOURCE_INTENT, open a database connection, change SQL
grants, delete evidence or activate operational intake. Its writer and reader
callbacks must be bound by the restricted runtime to the SAME authorised
period/run/capture. An SQL write acknowledgement is not proof of readback.
"""
import hashlib
import hmac
import re

from .ledger import Denied

BACKEND = 'PRIVATE_POSTGRES_V1'
CAPTURE_NAMES = frozenset(('capture-1/source.json', 'capture-2/source.json'))
SOURCE_BYTES_LIMIT = 524288
RECEIPT_FIELDS = frozenset(
    ('backend', 'period', 'run_id', 'name', 'sha256', 'bytes', 'readback_verified')
)


def verified_private_capture(raw, *, period, run_id, name, write, readback):
    """Write once then verify the ORIGINAL bytes via the authorised SQL reader.

    write(raw) is the existing scoped ingestion_intake_evidence_write call.
    readback() is the corresponding scoped ingestion_intake_evidence_read call;
    it must return the persisted bytea, not a recycled write acknowledgement.
    Neither function may switch credentials, extend a grant or retry a write.
    A rejected/unrecognised acknowledgement or uncertain read raises a fixed
    Denied reason; the caller retains the existing stop/reconcile requirement.
    """
    if (type(raw) is not bytes or len(raw) > SOURCE_BYTES_LIMIT
            or not callable(write) or not callable(readback)):
        raise Denied('PRIVATE_EVIDENCE_SOURCE_BOUND')
    if (type(period) is not str or re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', period) is None
            or type(run_id) is not str or re.fullmatch(r'[a-f0-9]{32}', run_id) is None
            or name not in CAPTURE_NAMES):
        raise Denied('PRIVATE_EVIDENCE_SCOPE_BOUND')
    sha = hashlib.sha256(raw).hexdigest()
    # Do not retry a write with unknown effects. The caller must reconcile via
    # exact-name/hash readback before any further execution.
    ack = write(raw)
    if (type(ack) is not dict or type(ack.get('bytes')) is not int
            or ack['bytes'] != len(raw) or ack.get('sha256') != sha
            or ack.get('readback_verified') is not False):
        raise Denied('PRIVATE_EVIDENCE_WRITE_ACK_UNVERIFIED')
    persisted = readback()
    if (type(persisted) is not bytes or len(persisted) != len(raw)
            or not hmac.compare_digest(persisted, raw)
            or not hmac.compare_digest(hashlib.sha256(persisted).hexdigest(), sha)):
        raise Denied('PRIVATE_EVIDENCE_READBACK_MISMATCH')
    return dict(backend=BACKEND, period=period, run_id=run_id, name=name,
                sha256=sha, bytes=len(raw), readback_verified=True)


def require_private_receipt(receipt, raw):
    """Validate the new discriminated receipt; forbid spoofed Git fields.

    A receipt's verified flag is meaningful only when issued by
    verified_private_capture with the original scoped SQL readback. This
    shape validation does not grant authority or substitute for that read.
    """
    if (type(receipt) is not dict or set(receipt) != RECEIPT_FIELDS
            or receipt.get('backend') != BACKEND or receipt.get('readback_verified') is not True
            or type(raw) is not bytes or type(receipt.get('bytes')) is not int
            or receipt['bytes'] != len(raw) or receipt['bytes'] > SOURCE_BYTES_LIMIT
            or receipt.get('sha256') != hashlib.sha256(raw).hexdigest()):
        raise Denied('DURABLE_ARCHIVE_NOT_VERIFIED')
    if (type(receipt.get('period')) is not str or re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', receipt['period']) is None
            or type(receipt.get('run_id')) is not str or re.fullmatch(r'[a-f0-9]{32}', receipt['run_id']) is None
            or receipt.get('name') not in CAPTURE_NAMES):
        raise Denied('DURABLE_ARCHIVE_NOT_VERIFIED')
    return receipt
