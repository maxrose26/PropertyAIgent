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
    def __init__(self, scope_binding, contract, rule, urls, *, revision, bindings, capture_authority, chain_authority, stop_file=None, allow_test_evidence=False, engine_options=None, capture_screening_only=False):
        if type(capture_screening_only) is not bool:raise Denied('CAPTURE_SCREENING_MODE')
        if capture_screening_only and scope_binding.council!='oldham':raise Denied('CAPTURE_SCREENING_COUNCIL')
        self.capture_screening_only=capture_screening_only
        self.engine_options=dict(engine_options or {})
        self.sb, self.contract, self.rule, self.urls, self.revision = scope_binding, contract, rule, urls, revision
        self.bindings, self.capture_authority, self.chain_authority = bindings, capture_authority, chain_authority      # `bindings` is shared with the registration(s) that fill it
        self.stop_file, self.allow_test_evidence = stop_file, allow_test_evidence
        self.registration = None
        self.preflighted = None
        self.budgets, self.accounting = [], {}
        self.listing_requests = []      # stays empty: no stage requests a listing
        self.capture_receipt = self.prior = None

    # ---------------------------------------------------------------------------------------------------------- plumbing
    def _budget(self, **kw):
        budget = DatabaseBudget(stop_file=self.stop_file, **kw) if self.stop_file else DatabaseBudget(**kw)
        self.budgets.append(budget)
        return budget

    def _coordinator(self, budget, authority, contracts):
        worker, broker = [budget.engine(self.urls[r],**self.engine_options) for r in ROLES[:2]]
        app=None if self.capture_screening_only else budget.engine(self.urls[ROLES[2]],**self.engine_options)
        ledger = ControllerLedger(worker, budget=budget, owner=WORKER, authority=authority, bindings=self.bindings, broker_engine=broker, application_engine=app)
        return Coordinator(ledger, contracts, screening_rules={V3_CONTRACT: self.rule})

    def _contracts(self):
        facts = self.registration.factual_contracts if self.registration else {}
        return {self.contract.name: self.contract, **{c.name: c for c in facts.values()}}

    def use(self, registration):
        """Adopt the prepared CHAIN registration (its bindings must already be the ones the authority was issued against)."""
        if self.capture_screening_only and registration.kind!='SCREENING':raise Denied('CAPTURE_SCREENING_NO_ADMISSION')
        if registration.kind not in ('CHAIN','SCREENING','ADMISSION') or registration.root_key != self.root_key:
            raise Denied('CHAIN_REGISTRATION_MISMATCH')
        self.registration = registration
        if registration.kind in ('SCREENING','ADMISSION'):self.chain_authority=registration.authority
        return self

    root_key = None

    # ------------------------------------------------------------------------------------------------------------ stages
    def preflight(self, root_key):
        """Before ANY source work: the registered root's own limits must fit the selected reader, supervisor and ledger. Read through the restricted ledger, not taken from the caller."""
        from .idox_target import COUNCILS
        if self.sb.council in COUNCILS:
            from .scope_binding import check_contract
            scope=self.contract.scope();check_contract(self.sb,self.contract,scope['start'],scope['end'])
        self.root_key = root_key
        budget = self._budget()
        co = self._coordinator(budget, self.capture_authority, {self.contract.name: self.contract})
        try:
            row = co.ledger.get(root_key)
            if row['subject'] != self.contract.scope() or row['contract'] != self.contract.name or row['task'] != 'DISCOVERY':
                raise Denied('CHAIN_FOREIGN_CAPTURE')
            layers = reconcile_items(self.sb, row['limits'])
            self.preflighted = root_key
            return layers
        finally:
            self.accounting['preflight'] = budget.close([])

    def capture(self, source, outer, *, expected_source_sha256, evidence_label, archive):
        """Retained capture: validate, archive with verified readback, checkpoint, finish. No listing request, no source spend."""
        if self.root_key is None or self.preflighted != self.root_key:
            raise Denied('PREFLIGHT_REQUIRED')      # no capture is stored for a root whose limits were not reconciled first
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
        from .scope_binding import check_capture
        check_capture(self.sb,self.contract,saved)
        self.capture_receipt = saved
        return saved

    def nominees(self, receipts=None):
        return derive_nominees([self.capture_receipt] if receipts is None else receipts, self.rule, allow_test_evidence=self.allow_test_evidence)

    def screen(self):
        if self.registration.kind=='ADMISSION':raise Denied('STAGED_SCREENING_REPLAY_FORBIDDEN')
        costs = []
        for batch in self.registration.batches:
            budget = self._budget(slot_key=batch['key'])
            co = self._coordinator(budget, self.chain_authority, self._contracts())
            try:
                process_batch(co, batch['key'], check=budget.check)
            finally:
                costs.append(budget.close([]))
        self.accounting['screening'] = costs

    def read_screening(self):
        """One accounted connection; all completed batch/assessment evidence, never a new assessment."""
        from .chain_registration import completed_screening
        budget=self._budget()
        co=self._coordinator(budget,self.chain_authority,self._contracts())
        try:
            from sqlalchemy import select
            from app.ingestion.schema import WorkItem
            keys=[r['key'] for r in [*self.registration.batches,*self.registration.screens.values()]]
            if any(k not in co.ledger.bindings for k in keys):raise Denied('STAGED_READBACK_BINDING')
            with co.ledger.worker_engine.begin() as connection:
                co.ledger._limits(connection)
                rows=[dict(row) for row in connection.execute(select(WorkItem).where(WorkItem.c.key.in_(keys)).order_by(WorkItem.c.key)).mappings()]
            completed_screening(self.registration,self.capture_receipt,self.rule,rows)
            return rows
        finally:self.accounting['screening_readback']=budget.close([])

    def screening_outcome(self, reference):
        budget = self._budget()
        co = self._coordinator(budget, self.chain_authority, self._contracts())
        try:
            return (co.ledger.get(self.registration.screens[reference]['key'])['checkpoint'] or {}).get('count_assessment', {}).get('admission')
        finally:
            self.accounting.setdefault('reads', []).append(budget.close([]))

    def prepare(self, nominee):
        if self.capture_screening_only:raise Denied('CAPTURE_SCREENING_NO_ADMISSION')
        """Everything one admission needs, built from the restricted ledger's retained state and the nominee: nothing is taken from the caller's memory of the capture."""
        reg, receipt = self.registration, self.capture_receipt
        from .scope_binding import check_capture
        check_capture(self.sb,self.contract,receipt)
        from .idox_target import COUNCILS
        if self.sb.council in COUNCILS and nominee not in derive_nominees([receipt],self.rule,allow_test_evidence=self.allow_test_evidence).nominees:raise Denied('CLOSED_IDOX_NOMINEE_BINDING')
        if nominee.reference not in reg.facts:
            raise Denied('CHAIN_NOMINEE_NOT_REGISTERED')
        record = next(r for r in receipt['records'] if r['reference'] == nominee.reference)
        batch = reg.batches[receipt['records'].index(record) // 5]
        fc = reg.factual_contracts[nominee.reference]
        from .idox_target import COUNCILS
        if self.sb.council in COUNCILS:
            from .scope_binding import check_detail_target
            check_detail_target(self.sb,record,fc.row)
            if fc.verification_scope!='COUPLED':raise Denied('CLOSED_IDOX_FACTUAL_SCOPE')
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

    def closed_idox_detail(self, adm, *, root, memory_group=None, observe=None):
        if self.capture_screening_only:raise Denied('CAPTURE_SCREENING_NO_DETAIL')
        """Bind the existing private source transport to ONE prepared factual item."""
        from .idox_target import COUNCILS,validate
        if self.sb.council not in COUNCILS:raise Denied('CLOSED_IDOX_COUNCIL')
        target=self.registration.factual_contracts[adm.nominee.reference].row
        validate(target)
        def read(row):
            if row['key']!=adm.fact['key'] or row['contract']!=adm.binding.factual_contract:raise Denied('CLOSED_IDOX_FACTUAL_TASK')
            record=next(r for r in self.capture_receipt['records'] if r['reference']==adm.nominee.reference)
            from .scope_binding import check_detail_target
            check_detail_target(self.sb,record,target)
            from .operational_source import read as source_read
            return source_read('detail',target,root=root,stop_file=self.stop_file,memory_group=memory_group,observe=observe,closed_target=True)
        return read

    def admit(self, adm, detail_reader):
        if self.capture_screening_only:raise Denied('CAPTURE_SCREENING_NO_ADMISSION')
        """One nominee: fresh detail verification, shared identity admission, B2, committed readback. `detail_reader` is the caller's bounded detail source for the nominated case."""
        try:
            return execute(adm.co, adm.binding, listing_reader=self.no_listing, detail_reader=detail_reader, envelope=adm.envelope, council=adm.council, check=adm.budget.check,
                           allow_test_evidence=self.allow_test_evidence)
        finally:
            self.accounting.setdefault('admission', []).append(adm.budget.close([]))
