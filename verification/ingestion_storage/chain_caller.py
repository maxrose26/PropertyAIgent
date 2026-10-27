"""The integrated chain's caller (dormant: nothing imports it, schedules it or runs it live).

Drives the stages of the bounded end-to-end connection through the production entry points on the three restricted logins, in order:

  retained capture -> batch screening (frozen v3) -> nominees -> fresh detail verification -> shared identity admission and B2 -> committed readback

It never requests a listing, never holds a connection outside a closed `DatabaseBudget`, and takes every authority from a registration prepared by `chain_registration` (it names no key
itself). The source audit and the outer-supervisor object are INPUTS: the caller does not run or supervise a source. A source reader runs under the release's own supervisor and its slot
receipt supplies the outer object (`verification.discovery.outer_evidence.outer_from_slot_receipt`).
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import get_council
from app.ingestion.batching import process_batch
from app.ingestion.coordinator import Coordinator
from app.ingestion.ledger import Denied, digest
from app.ingestion.listing_screening import V3_CONTRACT, code_binding
from app.ingestion.nomination import derive_nominees
from app.pipeline.discovery_contract import DiscoveryEnvelope, WindowEvidence
from .limit_reconciliation import reconcile_items
from .operational_controller import AcceptanceBinding, ControllerLedger, DatabaseBudget, execute
from .v3_admission import V3AdmissionBinding, factual_binding

ROLES = ('ingestion_worker_login', 'ingestion_effect_login', 'ingestion_application_login')
WORKER = 'required_once'      # the worker name `Owner.build_grant` puts in every grant
LEASE_SECONDS = 165


@dataclass
class Admission:
    co: object
    binding: object
    budget: object
    envelope: object
    council: object
    nominee: object
    fact: dict


class ChainCaller:
    def __init__(self, scope_binding, contract, rule, urls, *, revision, bindings, capture_authority, chain_authority, stop_file=None, allow_test_evidence=False):
        self.sb, self.contract, self.rule, self.urls, self.revision = scope_binding, contract, rule, urls, revision
        self.bindings, self.capture_authority, self.chain_authority = bindings, capture_authority, chain_authority      # `bindings` is shared with the registration(s) that fill it
        self.stop_file, self.allow_test_evidence = stop_file, allow_test_evidence
        self.registration = None
        self.budgets, self.accounting = [], {}
        self.listing_requests = []      # stays empty: no stage requests a listing
        self.capture_receipt = self.prior = None

    # ---------------------------------------------------------------------------------------------------------- plumbing
    def _budget(self, **kw):
        budget = DatabaseBudget(stop_file=self.stop_file, **kw) if self.stop_file else DatabaseBudget(**kw)
        self.budgets.append(budget)
        return budget

    def _coordinator(self, budget, authority, contracts):
        worker, broker, app = [budget.engine(self.urls[r]) for r in ROLES]
        ledger = ControllerLedger(worker, budget=budget, owner=WORKER, authority=authority, bindings=self.bindings, broker_engine=broker, application_engine=app)
        return Coordinator(ledger, contracts, screening_rules={V3_CONTRACT: self.rule})

    def _contracts(self):
        facts = self.registration.factual_contracts if self.registration else {}
        return {self.contract.name: self.contract, **{c.name: c for c in facts.values()}}

    def use(self, registration):
        """Adopt the prepared CHAIN registration (its bindings must already be the ones the authority was issued against)."""
        if registration.kind != 'CHAIN' or registration.root_key != self.root_key:
            raise Denied('CHAIN_REGISTRATION_MISMATCH')
        self.registration = registration
        return self

    root_key = None

    # ------------------------------------------------------------------------------------------------------------ stages
    def preflight(self, root_key):
        """Before ANY source work: the registered root's own limits must fit the selected reader, supervisor and ledger. Read through the restricted ledger, not taken from the caller."""
        self.root_key = root_key
        budget = self._budget()
        co = self._coordinator(budget, self.capture_authority, {self.contract.name: self.contract})
        try:
            row = co.ledger.get(root_key)
            if row['subject'] != self.contract.scope() or row['contract'] != self.contract.name or row['task'] != 'DISCOVERY':
                raise Denied('CHAIN_FOREIGN_CAPTURE')
            return reconcile_items(self.sb, row['limits'])
        finally:
            self.accounting['preflight'] = budget.close([])

    def capture(self, source, outer, *, expected_source_sha256, evidence_label, archive):
        """Retained capture: validate, archive with verified readback, checkpoint, finish. No listing request, no source spend."""
        budget = self._budget(slot_key=self.root_key)
        co = self._coordinator(budget, self.capture_authority, {self.contract.name: self.contract})
        try:
            claim = co.ledger.claim(self.root_key, lease_seconds=LEASE_SECONDS)
            self.capture_receipt = co.retained_capture(claim, source, outer, archive, expected_source_sha256=expected_source_sha256, evidence_label=evidence_label)
            return self.capture_receipt
        finally:
            self.accounting['capture'] = budget.close([])

    def read_capture(self):
        """The checkpoint as the restricted ledger holds it: what every later stage consumes, not the caller's memory."""
        budget = self._budget()
        co = self._coordinator(budget, self.capture_authority, {self.contract.name: self.contract})
        try:
            saved = co.ledger.get(self.root_key)['checkpoint']
            budget.capture_checkpoint_sha256 = digest(saved)
        finally:
            self.prior = budget.close([])
        self.capture_receipt = saved
        return saved

    def nominees(self, receipts=None):
        return derive_nominees(receipts or [self.capture_receipt], self.rule, allow_test_evidence=self.allow_test_evidence)

    def screen(self):
        costs = []
        for batch in self.registration.batches:
            budget = self._budget(slot_key=batch['key'])
            co = self._coordinator(budget, self.chain_authority, self._contracts())
            try:
                process_batch(co, batch['key'], check=budget.check)
            finally:
                costs.append(budget.close([]))
        self.accounting['screening'] = costs

    def screening_outcome(self, reference):
        budget = self._budget()
        co = self._coordinator(budget, self.chain_authority, self._contracts())
        try:
            return (co.ledger.get(self.registration.screens[reference]['key'])['checkpoint'] or {}).get('count_assessment', {}).get('admission')
        finally:
            self.accounting.setdefault('reads', []).append(budget.close([]))

    def prepare(self, nominee):
        """Everything one admission needs, built from the restricted ledger's retained state and the nominee: nothing is taken from the caller's memory of the capture."""
        reg, receipt = self.registration, self.capture_receipt
        record = next(r for r in receipt['records'] if r['reference'] == nominee.reference)
        batch = reg.batches[receipt['records'].index(record) // 5]
        fc = reg.factual_contracts[nominee.reference]
        budget = self._budget(previous=self.prior)
        co = self._coordinator(budget, self.chain_authority, self._contracts())
        nom = AcceptanceBinding(self.root_key, reg.screens[nominee.reference]['key'], reg.facts[nominee.reference]['key'], record['reference'], record['source_url'], record['source_record_id'],
                                digest(record), digest(receipt), digest(self.prior), batch['key'])
        binding = V3AdmissionBinding(nom, self.sb.council, self.contract.name, self.revision, digest(self.rule.config()), digest(code_binding()), fc.name, self.revision, factual_binding(fc))
        scope = self.contract.scope()
        placeholder = WindowEvidence(self.sb.council, 'chain-caller-placeholder', *[datetime.fromisoformat(scope[k]).date() for k in ('start', 'end', 'start', 'end')], scope['semantics'],
                                     'chain', 'date-labels', 'terminal-count', 1, 1, 2, 2000, 1)      # replaced by the contract's own re-derived window inside the shared admission
        env = DiscoveryEnvelope(self.sb.council, record['reference'], record['source_url'], record['source_record_id'], datetime.now(timezone.utc), placeholder, (record['reference'],), 'a' * 64, ())
        return Admission(co, binding, budget, env, get_council(self.sb.council), nominee, reg.facts[nominee.reference])

    def probe_claim(self, key):
        """Try to claim an item through a FRESH accounted budget that is always closed."""
        budget = self._budget()
        co = self._coordinator(budget, self.chain_authority, self._contracts())
        try:
            return co.ledger.claim(key, lease_seconds=LEASE_SECONDS)
        finally:
            self.accounting.setdefault('probes', []).append(budget.close([]))

    def no_listing(self, _):
        self.listing_requests.append(1)
        raise Denied('CHAIN_NEVER_LISTS')

    def admit(self, adm, detail_reader):
        """One nominee: fresh detail verification, shared identity admission, B2, committed readback. `detail_reader` is the caller's bounded detail source for the nominated case."""
        try:
            return execute(adm.co, adm.binding, listing_reader=self.no_listing, detail_reader=detail_reader, envelope=adm.envelope, council=adm.council, check=adm.budget.check,
                           allow_test_evidence=self.allow_test_evidence)
        finally:
            self.accounting.setdefault('admission', []).append(adm.budget.close([]))
