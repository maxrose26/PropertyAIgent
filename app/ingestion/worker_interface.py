"""Scoped worker-facing claim/checkpoint API over the existing disposable Ledger.

This is an interface rehearsal, not a Python security sandbox or a production
SQL capability. No grants, barrier release, effects, recovery or consumers.
The controller supplies the immutable finite binding and trusted validator.
"""
from dataclasses import dataclass
from types import MappingProxyType
import re
from .ledger import Claim, Denied, Ledger, bounded, digest


@dataclass(frozen=True)
class TaskBinding:
    key: str
    task: str
    contract: str
    revision: str
    subject_sha256: str


class WorkerInterface:
    """Workers choose only a prebound key; identity/authority are controller-set.

    All atomic eligibility, dependency, attempt, global-stop and fencing checks
    remain in Ledger. Validators must be pure and perform no external effects.
    No engine, authority issuer, enqueue, intent, writer or recover API is exposed.
    Private Python attributes remain reachable to trusted in-process code; real
    restricted-login SQL enforcement remains an outstanding production change.
    """
    __slots__ = ('_ledger', '_owner', '_authority', '_bindings', '_validators')

    def __init__(self, ledger, *, owner, authority, bindings, validators):
        if type(ledger) is not Ledger:
            raise Denied('EXISTING_DISPOSABLE_LEDGER_REQUIRED')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', owner):
            raise Denied('WORKER_IDENTITY')
        if not re.fullmatch(r'INGESTION_TEST_[A-Za-z0-9_-]{1,70}', authority):
            raise Denied('NO_LIVE_WORKER_AUTHORITY')
        bindings = tuple(bindings)
        if not 1 <= len(bindings) <= 60 or any(type(b) is not TaskBinding for b in bindings):
            raise Denied('FINITE_TASK_BINDING')
        if len({b.key for b in bindings}) != len(bindings):
            raise Denied('FINITE_TASK_BINDING')
        for b in bindings:
            if type(b) is not TaskBinding or not re.fullmatch('[a-f0-9]{64}', b.key):
                raise Denied('TASK_BINDING')
            if b.task not in {'DISCOVERY', 'LISTING_METADATA', 'SCREENING', 'FACTUAL_REFRESH'}:
                raise Denied('TASK_BINDING')
            if not callable(validators.get(b.contract)):
                raise Denied('TRUSTED_CHECKPOINT_VALIDATOR_REQUIRED')
        self._ledger = ledger
        self._owner = owner
        self._authority = authority
        self._bindings = MappingProxyType({b.key: b for b in bindings})
        self._validators = MappingProxyType(dict(validators))
        for b in bindings:
            self._bound(b.key)

    def _bound(self, key):
        binding = self._bindings.get(key)
        if binding is None:
            raise Denied('TASK_NOT_BOUND')
        row = self._ledger.get(key)
        if (row['task'], row['contract'], row['revision'], digest(row['subject'])) != (
            binding.task, binding.contract, binding.revision, binding.subject_sha256
        ):
            raise Denied('TASK_BINDING_CHANGED')
        return row

    def claim(self, key, *, lease_seconds=120):
        self._bound(key)
        # No queue membership or binding substitutes for a registered allowance.
        return self._ledger.claim(key, self._owner, self._authority, lease_seconds)

    def checkpoint(self, claim, evidence):
        if type(claim) is not Claim or claim.owner != self._owner:
            raise Denied('WORKER_CLAIM_IDENTITY')
        row = self._bound(claim.key)
        if row['authority'] != self._authority:
            raise Denied('WORKER_AUTHORITY_BINDING')
        # Refuse any effect-intent resolution through this offline seam. Existing
        # coordinator/source/B2 contracts retain their own closure/readback gate.
        if row['phase'] not in {'CLAIMED', 'CHECKPOINTED'}:
            raise Denied('EFFECT_RESOLUTION_NOT_EXPOSED')
        receipt = bounded(evidence, min(128 * 1024, row['limits']['audit_bytes']))
        if self._validators[row['contract']](bounded(row), receipt) is not True:
            raise Denied('CHECKPOINT_CONTRACT')
        self._ledger.checkpoint(claim, receipt)  # Rechecks fence/lease/authority.
        return digest(receipt)
