"""The integrated chain's caller (dormant: nothing imports it, schedules it or runs it live).

Drives the stages of the bounded end-to-end connection through the production entry points on the three restricted logins, in order:

  retained capture -> batch screening (frozen v3) -> nominees -> fresh detail verification -> shared identity admission and B2 -> committed readback

It never requests a listing, never holds a connection outside a closed `DatabaseBudget`, and takes every authority from a registration prepared by `chain_registration` (it names no key
itself). The source audit and the outer-supervisor object are INPUTS: the caller does not run or supervise a source. A source reader runs under the release's own supervisor and its slot
receipt supplies the outer object (`verification.discovery.outer_evidence.outer_from_slot_receipt`).
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import time

from app.config import get_council
from app.ingestion.batching import process_batch
from app.ingestion.coordinator import Coordinator
from app.ingestion.ledger import Denied, digest
from app.ingestion.listing_screening import V3_CONTRACT, code_binding
from app.ingestion.nomination import derive_nominees
from app.pipeline.discovery_contract import DiscoveryEnvelope, WindowEvidence
from .limit_reconciliation import reconcile_items,INTAKE_SCOPE_SECONDS
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
    intake_run = None  # historical callers/test adapters predate the opt-in run envelope
    def __init__(self, scope_binding, contract, rule, urls, *, revision, bindings, capture_authority, chain_authority, stop_file=None, allow_test_evidence=False, engine_options=None, capture_screening_only=False, intake_only=False,intake_run=None):
        if type(intake_only) is not bool:raise Denied('INTAKE_MODE')
        self.intake_only=intake_only
        self.intake_run=intake_run
        if type(capture_screening_only) is not bool:raise Denied('CAPTURE_SCREENING_MODE')
        if capture_screening_only and scope_binding.council!='oldham':raise Denied('CAPTURE_SCREENING_COUNCIL')
        self.capture_screening_only=capture_screening_only
        self.engine_options=dict(engine_options or {})
        self.sb, self.contract, self.rule, self.urls, self.revision = scope_binding, contract, rule, urls, revision
        self.bindings, self.capture_authority, self.chain_authority = bindings, capture_authority, chain_authority      # `bindings` is shared with the registration(s) that fill it
        self.stop_file, self.allow_test_evidence = stop_file, allow_test_evidence
        self.registration = None
        self.intake_started=time.monotonic()
        self.preflighted = None
        self.budgets, self.accounting = [], {}
        self.listing_requests = []      # stays empty: no stage requests a listing
        self.capture_receipt = self.prior = None

    # ---------------------------------------------------------------------------------------------------------- plumbing
    def _budget(self, **kw):
        if self.intake_only:
            # Reuse the existing finite database envelope across ALL stages of
            # this intake scope, including readbacks and duplicate deliveries.
            # A caller cannot reset it by starting another logical batch.
            statements=sum(b.statements for b in self.budgets)
            attempts=sum(b.attempts for b in self.budgets)
            returned=sum(b.returned_bytes for b in self.budgets)
            left=INTAKE_SCOPE_SECONDS-(time.monotonic()-self.intake_started)-30
            if statements>1040-36 or attempts>40-3 or returned>=4*1024**2 or left<=0:
                raise Denied('INTAKE_AGGREGATE_CLOSURE_RESERVE')
            kw.update(statements=min(kw.get('statements',120),1040-statements-16),
                      connections=min(kw.get('connections',16),40-attempts-2),
                      returned_bytes=min(kw.get('returned_bytes',4*1024**2),4*1024**2-returned),
                      seconds=min(kw.get('seconds',165),left))
            kw['cancel_used']=sum(b.prior_cancel_attempts+sum(e.get('cancel_attempts',0) for e in b.hard_deadline_events) for b in self.budgets)
        if self.intake_run is not None:kw=self.intake_run.database_limits(kw)
        budget = DatabaseBudget(stop_file=self.stop_file, **kw) if self.stop_file else DatabaseBudget(**kw)
        if self.intake_run is not None:self.intake_run.budgets.append(budget)
        if self.intake_only:budget.hard_stop_at=self.intake_started+INTAKE_SCOPE_SECONDS-30
        self.budgets.append(budget)
        return budget

    def _coordinator(self, budget, authority, contracts):
        worker, broker = [budget.engine(self.urls[r],**self.engine_options) for r in ROLES[:2]]
        app=None if self.capture_screening_only or self.intake_only else budget.engine(self.urls[ROLES[2]],**self.engine_options)
        ledger = ControllerLedger(worker, budget=budget, owner=WORKER, authority=authority, bindings=self.bindings, broker_engine=broker, application_engine=app)
        return Coordinator(ledger, contracts, screening_rules={V3_CONTRACT: self.rule},capture_bound_screening=self.intake_only,
                           isolated_contracts=(self.contract.name,) if self.intake_run is not None else ())

    def _contracts(self):
        facts = self.registration.factual_contracts if self.registration else {}
        return {self.contract.name: self.contract, **{c.name: c for c in facts.values()}}

    def use(self, registration):
        """Adopt the prepared CHAIN registration (its bindings must already be the ones the authority was issued against)."""
        if (self.capture_screening_only or self.intake_only) and registration.kind!='SCREENING':raise Denied('CAPTURE_SCREENING_NO_ADMISSION')
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

    def claim_intake_capture(self):
        """Check the existing DB stop/authority before an externally permitted source.

        This claims retention work only. It does NOT grant a source allowance;
        the source release must separately journal and authorise collection.
        """
        if not self.intake_only or self.root_key is None or self.preflighted!=self.root_key:
            raise Denied('INTAKE_PREFLIGHT_REQUIRED')
        budget=self._budget(slot_key=self.root_key)
        co=self._coordinator(budget,self.capture_authority,{self.contract.name:self.contract})
        try:
            claim=co.ledger.claim(self.root_key,lease_seconds=LEASE_SECONDS)
            if self.intake_run is not None:co.ledger.intent(claim,'source_calls')
            return claim
        finally:self.accounting['intake_claim']=budget.close([])

    def settle_intake_failure(self,claim,category,source,outer,archive):
        from app.ingestion.batching import archive_capture
        budget=self._budget(slot_key=self.root_key)
        co=self._coordinator(budget,self.capture_authority,{self.contract.name:self.contract})
        try:
            if getattr(self,'before_archive',None):self.before_archive(co.ledger)
            receipt=archive_capture(source,archive)
            co.fail(claim,category,cleanup_closed=True,accounting_complete=True,council_isolated=True,
                    source_audit=source,outer=outer,failure_archive=receipt)
        finally:self.accounting['contained_failure']=budget.close([])

    def capture(self, source, outer, *, expected_source_sha256, evidence_label, archive, observed_at=None, intake_claim=None):
        """Retained capture: validate, archive with verified readback, checkpoint, finish. No listing request, no source spend."""
        if self.root_key is None or self.preflighted != self.root_key:
            raise Denied('PREFLIGHT_REQUIRED')      # no capture is stored for a root whose limits were not reconciled first
        budget = self._budget(slot_key=self.root_key)
        co = self._coordinator(budget, self.capture_authority, {self.contract.name: self.contract})
        try:
            if intake_claim is not None and (not self.intake_only or intake_claim.key!=self.root_key):raise Denied('INTAKE_CLAIM_BINDING')
            claim = intake_claim if intake_claim is not None else co.ledger.claim(self.root_key, lease_seconds=LEASE_SECONDS)
            def checked_archive(raw):
                if getattr(self,'before_archive',None):self.before_archive(co.ledger)
                return archive(raw)
            self.capture_receipt = co.retained_capture(claim, source, outer, checked_archive, expected_source_sha256=expected_source_sha256, evidence_label=evidence_label, observed_at=observed_at)
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

    def read_intake_items(self, keys):
        """Bounded read of explicitly bound intake items, including unfinished work.

        No queue scan, claim, grant or application principal. Missing child rows
        are returned as absent, never promoted to completed screening.
        """
        if not self.intake_only:raise Denied('INTAKE_MODE_REQUIRED')
        keys=list(keys)
        if not keys or len(keys)>73 or len(set(keys))!=len(keys):raise Denied('INTAKE_READ_BOUND')
        budget=self._budget()
        co=self._coordinator(budget,self.chain_authority if self.registration else self.capture_authority,self._contracts())
        try:
            if any(k not in co.ledger.bindings for k in keys):raise Denied('TASK_NOT_BOUND')
            from sqlalchemy import select
            from app.ingestion.schema import WorkItem
            from app.ingestion.ledger import bounded
            with co.ledger.worker_engine.begin() as connection:
                co.ledger._limits(connection)
                rows=[dict(r) for r in connection.execute(select(WorkItem).where(WorkItem.c.key.in_(keys)).order_by(WorkItem.c.key)).mappings()]
            bounded(rows,2*1024**2)
            return rows
        finally:self.accounting.setdefault('intake_reads',[]).append(budget.close([]))

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
        if self.intake_only:raise Denied('INTAKE_NO_ADMISSION')
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
