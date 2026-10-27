"""The integrated test caller: one object that drives the whole chain through the PRODUCTION entry points and restricted disposable roles.

Only the OWNER STAND-INS (methods `owner_*`) use the bootstrap connection: they insert the work items and grants that the owner's registration ceremony would create, exactly as
the existing admission test does. Everything else is production code reached through `ControllerLedger` on the three restricted logins:

  retained_capture -> process_batch (frozen v3 screening) -> derive_nominees -> execute (execute_retained_v3 -> fresh detail -> shared admission and B2 -> committed readback)

Nothing here substitutes the processing path under test. All data are synthetic; archives are labelled test artefacts; no council or production database is contacted.
"""
import copy
import json
import time
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_council
from app.db.models import Application, Base
from app.ingestion.batching import batch_plans, process_batch
from app.ingestion.coordinator import Coordinator
from app.ingestion.ledger import DEFAULT_LIMITS, digest
from app.ingestion.listing_screening import RULE_V3, V3_CONTRACT, ScreeningRule, assessment_identity, code_binding
from app.ingestion.nomination import derive_nominees
from app.pipeline.discovery_contract import DiscoveryEnvelope, WindowEvidence
from tests.e2e_connection_support import (ASSESS, EXTENSION, LABEL, NO_COUNT, PARENT, SCHEME, BELOW, IsolatedTestPublisher, arcus_audit, arcus_contract, arcus_detail_audit,
                                          arcus_detail_target, entry, idox_audit, idox_contract, idox_detail, idox_detail_target, outer)
from verification.direct_reference.fixtures import summary
from verification.discovery.finite_acceptance import SEMANTICS
from verification.ingestion_storage.new_identity_contract import accepted_arcus_new_identity, accepted_idox_new_identity
from verification.ingestion_storage.operational_controller import AcceptanceBinding, ControllerLedger, DatabaseBudget, execute
from verification.ingestion_storage.retained_world import item
from verification.ingestion_storage.screening_v3_grant import apply_screening
from verification.ingestion_storage.v3_admission import V3AdmissionBinding, factual_binding

START, END = date(2026, 11, 9), date(2026, 11, 15)
MIXED = [entry('E2E/1/26', SCHEME), entry('E2E/2/26', ASSESS), entry('E2E/3/26', NO_COUNT), entry('E2E/4/26', EXTENSION), entry('E2E/5/26', BELOW), entry('E2E/6/26', PARENT)]
FAMILY_COUNCIL = {'idox': 'tameside', 'arcus': 'manchester'}
AUTH_CAPTURE, AUTH_CHAIN = 'INGESTION_TEST_e2e_capture', 'INGESTION_TEST_e2e_chain'
ROLES = ['ingestion_worker_login', 'ingestion_effect_login', 'ingestion_application_login']
APPLICATION_COLUMNS = ['id', 'council_code', 'reference', 'status', 'decision', 'decision_issued_date', 'status_verified_at', 'planning_field_verification', 'unit_confirmation_status', 'site_id', 'proposal', 'address',
                       'application_type', 'estimated_unit_count', 'opportunity_classification']


def snapshot(boot):
    """(row count, content hash) of every application-schema table: the write-set evidence."""
    out = {}
    for table in Base.metadata.sorted_tables:
        out[table.name] = boot.execute(f'SELECT count(*), coalesce(md5(string_agg(t::text, \'|\' ORDER BY t::text)), \'\') FROM {table.name} t').fetchone()
    return out


def changed_tables(before, after):
    return sorted(name for name in before if before[name] != after[name])


def application(boot, council, reference):
    row = boot.execute('SELECT ' + ','.join(APPLICATION_COLUMNS) + ' FROM applications WHERE council_code=%s AND reference=%s', (council, reference)).fetchone()
    return dict(zip(APPLICATION_COLUMNS, row)) if row else None


def restricted_sessions(boot):
    return boot.execute('SELECT count(*) FROM pg_stat_activity WHERE usename = ANY(%s)', (ROLES,)).fetchone()[0]


@dataclass
class Admission:
    co: object
    binding: object
    budget: object
    envelope: object
    council: object
    detail: object
    detail_calls: list
    nominee: object
    fact: dict


class Chain:
    def __init__(self, world, tmp_path, family, tag, entries=None, *, council=None, publisher_mode='ok', stop_file=None, contract_revision=None):
        self.w, self.family, self.tag = world, family, tag
        self.council = council or FAMILY_COUNCIL[family]
        self.entries = entries if entries is not None else copy.deepcopy(MIXED)
        self.rule = ScreeningRule(RULE_V3, unit_threshold=10, link_related=False)
        self.publisher = IsolatedTestPublisher(tmp_path, publisher_mode)
        self.stop_file = stop_file
        self.auth_capture, self.auth_chain = f'{AUTH_CAPTURE}_{tag}', f'{AUTH_CHAIN}_{tag}'      # one pair of authorities per chain, so two captures can coexist
        self.revision = contract_revision or tag
        if family == 'idox':
            self.contract, self.audit = idox_contract(self.council, START, END), idox_audit(self.council, self.entries, START, END)
        else:
            self.contract, self.audit = arcus_contract(self.council, START, END), arcus_audit(self.council, self.entries, START, END)
        self.listing_requests = []      # the integrated caller never lists: this stays empty and every test asserts it
        self.budgets, self.accounting = [], {}
        self.root = item(dict(subject=self.contract.scope(), task='DISCOVERY', contract=self.contract.name, revision=self.revision))
        self.bindings = {}
        self.capture_receipt = None

    # ------------------------------------------------------------------------------------------------------------ plumbing
    def _budget(self, **kw):
        budget = DatabaseBudget(stop_file=self.stop_file, **kw) if self.stop_file else DatabaseBudget(**kw)
        self.budgets.append(budget)
        return budget

    def _coordinator(self, budget, authority, contracts):
        urls = self.w['urls']
        worker, broker, app = [budget.engine(urls[r]) for r in ROLES]
        ledger = ControllerLedger(worker, budget=budget, owner='one', authority=authority, bindings=self.bindings, broker_engine=broker, application_engine=app)
        return Coordinator(ledger, contracts, screening_rules={V3_CONTRACT: self.rule})

    def _control(self):
        return self.w['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]

    def _write_control(self, control):
        self.w['boot'].execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)", (json.dumps(control),))

    def _grant(self, keys, contracts, bindings, *, ttl, source_calls, writes, detail_keys=(), capture_only=False, outcomes=None):
        grant = dict(keys=list(keys), contracts=list(contracts), bindings=bindings, expires_at=time.time() + ttl, source_calls=source_calls, writes=writes, login='ingestion_worker_login',
                     effect_login='ingestion_effect_login', workers=['one'], detail_source_keys=list(detail_keys), completion_outcomes=copy.deepcopy(outcomes or {}))
        if capture_only:
            grant['capture_only'] = True
        return grant

    def _insert(self, row):
        self.w['boot'].execute('INSERT INTO ingestion_work_items SELECT * FROM json_populate_record(NULL::ingestion_work_items,%s::json)', (json.dumps(row),))

    # ------------------------------------------------------------------------------------------------ OWNER STAND-INS (bootstrap)
    def owner_reset(self):
        boot = self.w['boot']
        boot.execute('DELETE FROM ingestion_work_attempts')
        boot.execute("DELETE FROM ingestion_work_items WHERE key<>repeat('0',64)")
        boot.execute('TRUNCATE applications CASCADE')
        self._write_control(copy.deepcopy(self.w['control']))
        return self

    def owner_registers_capture(self, *, ttl=600, capture_only=False, outcomes=('ENUMERATED_METADATA_RETAINED',), source_calls=0, stop=None):
        control = self._control()
        binding = {k: self.root[k] for k in ('subject', 'task', 'contract', 'revision')}
        self.bindings[self.root['key']] = binding
        control['grants'][self.auth_capture] = self._grant([self.root['key']], [self.contract.name], {self.root['key']: binding}, ttl=ttl, source_calls=source_calls, writes=0,
                                                      capture_only=capture_only, outcomes={'DISCOVERY': list(outcomes)})
        if stop is not None:
            control['global_stop'] = stop
        self._write_control(control)
        self._insert(self.root)
        return self

    def target_for(self, record):
        if self.family == 'idox':
            return idox_detail_target(self.council, record)
        return arcus_detail_target(self.council, record)

    def owner_registers_chain(self, nominees, *, ttl=600, writes=None, source_calls=None, stop=None, extra_contracts=()):
        """Insert the batch and factual items the owner would create from the sealed nominee set, and the second authority that covers them."""
        receipt = self.capture_receipt
        plans = batch_plans(self.root['key'], receipt, self.rule)
        self.batches = [item({k: p[k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=p['dependencies'], checkpoint=p['checkpoint']) for p in plans]
        self.screens = {}
        for record in receipt['records']:
            subject = dict(kind='APPLICATION', council=self.council, reference=record['reference'])
            self.screens[record['reference']] = item(dict(subject=subject, task='SCREENING', contract=V3_CONTRACT, revision=assessment_identity(record, self.rule)[3]), dependencies=[self.root['key']])
        self.facts, self.factual_contracts = {}, {}
        by_reference = {r['reference']: r for r in receipt['records']}
        for n, nominee in enumerate(nominees):
            record = by_reference[nominee.reference]
            target = self.target_for(record)
            factory = accepted_idox_new_identity if self.family == 'idox' else accepted_arcus_new_identity
            fc = factory(f'e2e-fact-{self.family}-{n}', target)
            self.factual_contracts[nominee.reference] = fc
            subject = dict(kind='APPLICATION', council=self.council, reference=nominee.reference)
            self.facts[nominee.reference] = item(dict(subject=subject, task='FACTUAL_REFRESH', contract=fc.name, revision=self.tag), dependencies=[self.screens[nominee.reference]['key']])
        rows = [self.root, *self.batches, *self.screens.values(), *self.facts.values()]
        bindings = {r['key']: {k: r[k] for k in ('subject', 'task', 'contract', 'revision')} for r in rows}
        self.bindings.update(bindings)
        contracts = [self.contract.name, 'listing-batch-v1', V3_CONTRACT, *[c.name for c in self.factual_contracts.values()], *extra_contracts]
        n = len(nominees)
        grant = self._grant(bindings, contracts, bindings, ttl=ttl, source_calls=n if source_calls is None else source_calls, writes=2 * n if writes is None else writes,
                            detail_keys=[f['key'] for f in self.facts.values()],
                            outcomes={'LISTING_METADATA': ['BATCH_SCREENED'], 'FACTUAL_REFRESH': ['SUPPORTED_FACTS_VERIFIED', 'ALREADY_KNOWN'], 'SCREENING': []})
        apply_screening(grant, self.rule)
        control = self._control()
        control['grants'][self.auth_chain] = grant
        if stop is not None:
            control['global_stop'] = stop
        self._write_control(control)
        for row in [*self.batches, *self.facts.values()]:
            self._insert(row)
        return self

    def owner_sets_stop(self, reason='DISPOSABLE_TEST_STOP'):
        """A stop in the DISPOSABLE control record only; no stop is ever cleared or bypassed, and no production stop is read."""
        control = self._control()
        control['global_stop'] = {'reason': reason}
        self._write_control(control)

    def owner_expires(self, authority):
        control = self._control()
        control['grants'][authority]['expires_at'] = 0
        self._write_control(control)

    def tamper(self, key, path, value):
        """Fixture-only forgery of a stored checkpoint, to prove the production binding checks refuse it."""
        self.w['boot'].execute('UPDATE ingestion_work_items SET checkpoint=jsonb_set(checkpoint::jsonb, %s::text[], %s::jsonb)::json WHERE key=%s', (path, json.dumps(value), key))

    # ------------------------------------------------------------------------------------------------------------ PRODUCTION
    def capture(self, *, source=None, expected=None, label=LABEL):
        """Retained capture through the restricted worker and broker: validate, archive with verified readback, checkpoint, finish. No listing request."""
        budget = self._budget(slot_key=self.root['key'])
        co = self._coordinator(budget, self.auth_capture, {self.contract.name: self.contract})
        source = self.audit if source is None else source
        try:
            claim = co.ledger.claim(self.root['key'], lease_seconds=165)
            receipt = co.retained_capture(claim, source, outer(), self.publisher, expected_source_sha256=digest(self.audit) if expected is None else expected, evidence_label=label)
            self.capture_receipt = receipt
            return receipt
        finally:
            self.accounting['capture'] = budget.close([])

    def read_capture(self):
        """The checkpoint as the restricted ledger holds it (what every later stage consumes), not the caller's memory."""
        budget = self._budget()
        co = self._coordinator(budget, self.auth_capture, {self.contract.name: self.contract})
        try:
            saved = co.ledger.get(self.root['key'])['checkpoint']
            budget.capture_checkpoint_sha256 = digest(saved)
        finally:
            self.prior = budget.close([])
        self.capture_receipt = saved
        return saved

    def nominees(self, receipts=None):
        return derive_nominees(receipts or [self.capture_receipt], self.rule, allow_test_evidence=True)

    def _contracts(self):
        return {self.contract.name: self.contract, **{c.name: c for c in self.factual_contracts.values()}}

    def screen(self):
        costs = []
        for batch in self.batches:
            budget = self._budget(slot_key=batch['key'])
            co = self._coordinator(budget, self.auth_chain, self._contracts())
            try:
                process_batch(co, batch['key'], check=budget.check)
            finally:
                costs.append(budget.close([]))
        self.accounting['screening'] = costs

    def screening_outcome(self, reference):
        return self.w['boot'].execute('SELECT checkpoint::jsonb->\'count_assessment\'->>\'admission\' FROM ingestion_work_items WHERE key=%s', (self.screens[reference]['key'],)).fetchone()[0]

    def prepare(self, nominee, *, detail_status='Decided'):
        """Everything an admission needs, built from the restricted ledger's own retained state; mirrors the existing admission test's `scenario`."""
        receipt = self.capture_receipt
        record = next(r for r in receipt['records'] if r['reference'] == nominee.reference)
        index = receipt['records'].index(record)
        batch = self.batches[index // 5]
        target = self.target_for(record)
        fc = self.factual_contracts[nominee.reference]
        if self.family == 'idox':
            source = idox_detail(target, summary(record['reference'], status=detail_status, decision='Approve' if detail_status == 'Decided' else '', date='Mon 28 Sep 2026' if detail_status == 'Decided' else ''))
        else:
            source = arcus_detail_audit(target)
        calls = []
        def detail(_):
            calls.append(1)
            return source, outer()
        budget = self._budget(previous=self.prior)
        co = self._coordinator(budget, self.auth_chain, self._contracts())
        nom = AcceptanceBinding(self.root['key'], self.screens[nominee.reference]['key'], self.facts[nominee.reference]['key'], record['reference'], record['source_url'], record['source_record_id'],
                                digest(record), digest(receipt), digest(self.prior), batch['key'])
        binding = V3AdmissionBinding(nom, self.council, self.contract.name, self.revision, digest(self.rule.config()), digest(code_binding()), fc.name, self.tag, factual_binding(fc))
        window = WindowEvidence(self.council, 'e2e-placeholder', START, END, START, END, SEMANTICS[self.council], 'e2e', 'date-labels', 'terminal-count', 1, 1, 2, 2000, 1)
        env = DiscoveryEnvelope(self.council, record['reference'], record['source_url'], record['source_record_id'], datetime(2026, 11, 16, tzinfo=timezone.utc), window, (record['reference'],), 'a' * 64, ())
        return Admission(co, binding, budget, env, get_council(self.council), detail, calls, nominee, self.facts[nominee.reference])

    def probe_claim(self, key):
        """Try to claim a work item through a FRESH accounted budget that is always closed, so a probe can never leave an unaccounted connection behind."""
        budget = self._budget()
        co = self._coordinator(budget, self.auth_chain, self._contracts())
        try:
            return co.ledger.claim(key, lease_seconds=165)
        finally:
            self.accounting.setdefault('probes', []).append(budget.close([]))

    def no_listing(self, _):
        self.listing_requests.append(1)
        raise AssertionError('the integrated chain must never request a listing')

    def admit(self, adm, *, allow_test_evidence=True):
        try:
            return execute(adm.co, adm.binding, listing_reader=self.no_listing, detail_reader=adm.detail, envelope=adm.envelope, council=adm.council, check=adm.budget.check, allow_test_evidence=allow_test_evidence)
        finally:
            self.accounting.setdefault('admission', []).append(adm.budget.close([]))
