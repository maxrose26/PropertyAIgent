"""The integrated test harness: owner STAND-INS around the PRODUCTION owner preparation and the PRODUCTION chain caller.

What is production here: the scope binding, limit reconciliation, `Owner.build_grant`-based preparation of items/grants/bindings from the validated capture and nominees
(`chain_registration`), and every stage (`ChainCaller`) through `ControllerLedger` on the three restricted logins. What is a disposable stand-in: only the INSERTION of the prepared rows
and grant into the disposable control record (`_install`) -- the owner's `register`, which also registers the policy's named exception, accepts only the pinned Bolton scope today -- and the
fixture forgeries the tests apply to a prepared grant. Sources are produced by real supervised child processes (`idox_supervised`, `arcus_slot_supervised`) over synthetic audits.

All data are synthetic; archives are labelled test artefacts; no council or production database is contacted.
"""
import copy
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.db.models import Base
from app.ingestion.ledger import DEFAULT_LIMITS, digest
from app.ingestion.listing_screening import RULE_V3, ScreeningRule
from tests.e2e_connection_support import (ASSESS, EXTENSION, LABEL, NO_COUNT, PARENT, SCHEME, BELOW, IsolatedTestPublisher, arcus_audit, arcus_contract, arcus_detail_audit,
                                          arcus_detail_target, arcus_slot_supervised, entry, idox_audit, idox_contract, idox_detail, idox_detail_target, idox_supervised)
from verification.direct_reference.fixtures import summary
from verification.ingestion_storage.chain_caller import ROLES, ChainCaller
from verification.ingestion_storage.chain_registration import authority_name, capture_registration, chain_registration
from verification.ingestion_storage.limit_reconciliation import BROWSER_SOURCE_V2_ITEM_LIMITS
from verification.ingestion_storage.operational_owner import Owner
from verification.ingestion_storage.scope_binding import binding_for

START, END = date(2026, 11, 9), date(2026, 11, 15)
MIXED = [entry('E2E/1/26', SCHEME), entry('E2E/2/26', ASSESS), entry('E2E/3/26', NO_COUNT), entry('E2E/4/26', EXTENSION), entry('E2E/5/26', BELOW), entry('E2E/6/26', PARENT)]
FAMILY_COUNCIL = {'idox': 'tameside', 'arcus': 'manchester'}
OWNER_BINDINGS = dict(revision='a' * 40, workflow_sha256='b' * 64, manifest_sha256='c' * 64)      # what the owner's execution binding would carry; synthetic here
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
    return boot.execute('SELECT count(*) FROM pg_stat_activity WHERE usename = ANY(%s)', (list(ROLES),)).fetchone()[0]


@dataclass
class Admission:
    """The production admission bundle plus the fixture's detail source for the nominated case."""
    inner: object
    detail: object
    detail_calls: list

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def __setattr__(self, name, value):
        if name in ('inner', 'detail', 'detail_calls'):
            object.__setattr__(self, name, value)
        else:
            setattr(self.inner, name, value)      # a forged field lands on the production bundle that is actually admitted


class Chain:
    def __init__(self, world, tmp_path, family, tag, entries=None, *, council=None, publisher_mode='ok', stop_file=None, contract_revision=None, binding=None, audit=None, owner_acceptance=None):
        self.w, self.family, self.tag = world, family, tag
        self.tmp = tmp_path / ('src-' + tag)      # one directory per chain: two chains in one test never share supervised-source paths
        self.tmp.mkdir()
        self.council = council or FAMILY_COUNCIL[family]
        self.binding = binding or binding_for(self.council)
        self.entries = entries if entries is not None else copy.deepcopy(MIXED)
        self.rule = ScreeningRule(RULE_V3, unit_threshold=10, link_related=False)
        self.publisher = IsolatedTestPublisher(tmp_path, publisher_mode)
        self.revision = contract_revision or tag
        self.item_limits = BROWSER_SOURCE_V2_ITEM_LIMITS if self.binding.execution_budget else DEFAULT_LIMITS
        self.auth_capture, self.auth_chain = authority_name(self.binding, 'CAPTURE', self.revision), authority_name(self.binding, 'CHAIN', self.revision)
        budget = self.binding.execution_budget
        if family == 'idox':
            self.contract, self.audit = idox_contract(self.council, START, END, owner_acceptance=owner_acceptance), audit if audit is not None else idox_audit(self.council, self.entries, START, END)
        else:
            self.contract, self.audit = arcus_contract(self.council, START, END, budget=budget), arcus_audit(self.council, self.entries, START, END, budget=budget)
        self.bindings = {}
        self.caller = ChainCaller(self.binding, self.contract, self.rule, world['urls'], revision=self.revision, bindings=self.bindings, capture_authority=self.auth_capture,
                                  chain_authority=self.auth_chain, stop_file=stop_file, allow_test_evidence=True)
        self.root = None
        self.outer = None
        self.source = None
        self.chain_registration = None

    # ------------------------------------------------------------------------------------------------------------ views of the production caller
    listing_requests = property(lambda self: self.caller.listing_requests)
    accounting = property(lambda self: self.caller.accounting)
    capture_receipt = property(lambda self: self.caller.capture_receipt, lambda self, v: setattr(self.caller, 'capture_receipt', v))
    prior = property(lambda self: self.caller.prior)
    batches = property(lambda self: self.chain_registration.batches)
    screens = property(lambda self: self.chain_registration.screens)
    facts = property(lambda self: self.chain_registration.facts)
    factual_contracts = property(lambda self: self.chain_registration.factual_contracts)

    # ------------------------------------------------------------------------------------------------ OWNER STAND-INS (bootstrap)
    def _control(self):
        return self.w['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]

    def _write_control(self, control):
        self.w['boot'].execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)", (json.dumps(control),))

    def _owner(self, ttl):
        """The PRODUCTION Owner, used only for its grant preparation (no connection is ever opened by it here)."""
        return Owner(None, lambda *_: None, lambda: None, expiry=datetime.fromtimestamp(time.time() + ttl, timezone.utc), bindings=dict(OWNER_BINDINGS))

    def _install(self, registration, *, grant=None, stop=None):
        """DISPOSABLE stand-in for the insertion half of `Owner.register`: put the prepared rows and grant into the disposable control record. `grant` is a (possibly forged) copy."""
        control = self._control()
        control['grants'][registration.authority] = registration.grant if grant is None else grant
        if stop is not None:
            control['global_stop'] = stop
        self._write_control(control)
        self.bindings.update(registration.bindings)
        for row in registration.insert:
            self.w['boot'].execute('INSERT INTO ingestion_work_items SELECT * FROM json_populate_record(NULL::ingestion_work_items,%s::json)', (json.dumps(row),))

    def owner_reset(self):
        boot = self.w['boot']
        boot.execute('DELETE FROM ingestion_work_attempts')
        boot.execute("DELETE FROM ingestion_work_items WHERE key<>repeat('0',64)")
        boot.execute('TRUNCATE applications CASCADE')
        self._write_control(copy.deepcopy(self.w['control']))
        return self

    def owner_registers_capture(self, *, ttl=1800, capture_only=False, outcomes=None, source_calls=None, stop=None, item_limits=None):
        reg = capture_registration(self._owner(ttl), self.binding, self.contract, START.isoformat(), END.isoformat(), revision=self.revision, item_limits=item_limits or self.item_limits)
        grant = copy.deepcopy(reg.grant)      # fixture forgeries are applied to a COPY of what production prepared
        if capture_only:
            grant['capture_only'] = True
        if outcomes is not None:
            grant['completion_outcomes']['DISCOVERY'] = list(outcomes)
        if source_calls is not None:
            grant['source_calls'] = source_calls
        self._install(reg, grant=grant, stop=stop)
        self.root, self.capture_registration = reg.rows[0], reg
        return self

    def target_for(self, record):
        from verification.ingestion_storage.idox_target import COUNCILS,derive
        if self.council in COUNCILS:return derive(self.council,record)
        return idox_detail_target(self.council, record) if self.family == 'idox' else arcus_detail_target(self.council, record)

    def owner_registers_chain(self, nominees, *, ttl=1800, writes=None, source_calls=None, stop=None, others=()):
        """Prepare (PRODUCTION) the batch/screening/factual items and the chain grant from the saved capture and the nominees, then install them."""
        receipt = self.capture_receipt
        from verification.ingestion_storage.idox_target import COUNCILS
        selected={n.reference for n in nominees} if self.council in COUNCILS else {r['reference'] for r in receipt['records']}
        targets = {r['reference']: self.target_for(r) for r in receipt['records'] if r['reference'] in selected}
        reg = chain_registration(self._owner(ttl), self.binding, self.contract, dict(self.root, checkpoint=receipt), receipt, tuple(nominees), self.rule, targets, revision=self.revision, item_limits=self.item_limits,
                                 allow_test_evidence=True, other_receipts=others)
        grant = copy.deepcopy(reg.grant)
        if writes is not None:
            grant['writes'] = writes
        if source_calls is not None:
            grant['source_calls'] = source_calls
        self._install(reg, grant=grant, stop=stop)
        self.chain_registration = reg
        self.caller.use(reg)
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

    # ------------------------------------------------------------------------------------------------------------ PRODUCTION STAGES
    def supervised_source(self):
        """Run the (synthetic) source under its REAL supervisor once: the audit it wrote and the outer object that supervisor produced."""
        if self.source is None:
            if self.family == 'idox':
                self.source, self.outer = idox_supervised(self.tmp, self.audit)
            else:
                self.source, self.outer, self.slot_receipt = arcus_slot_supervised(self.tmp, self.audit, self.contract.scope())
        return self.source, self.outer

    def capture(self, *, source=None, expected=None, label=LABEL):
        supervised, outer = self.supervised_source()
        if self.caller.preflighted != self.root['key']:
            self.caller.preflight(self.root['key'])      # the caller refuses to capture without it
        return self.caller.capture(supervised if source is None else source, outer, expected_source_sha256=digest(supervised) if expected is None else expected,
                                   evidence_label=label, archive=self.publisher)

    def read_capture(self):
        return self.caller.read_capture()

    def nominees(self, receipts=None):
        return self.caller.nominees(receipts)

    def screen(self):
        return self.caller.screen()

    def screening_outcome(self, reference):
        return self.caller.screening_outcome(reference)

    def probe_claim(self, key):
        return self.caller.probe_claim(key)

    def prepare(self, nominee, *, detail_status='Decided'):
        """The production admission bundle plus the fixture's detail source for the nominated case."""
        record = next(r for r in self.capture_receipt['records'] if r['reference'] == nominee.reference)
        target = self.target_for(record)
        if self.family == 'idox':
            source = idox_detail(target, summary(record['reference'], status=detail_status, decision='Approve' if detail_status == 'Decided' else '', date='Mon 28 Sep 2026' if detail_status == 'Decided' else ''))
        else:
            source = arcus_detail_audit(target)
        calls = []

        def detail(_):
            calls.append(1)
            return source, self.outer
        return Admission(self.caller.prepare(nominee), detail, calls)

    def admit(self, adm, *, allow_test_evidence=True):
        self.caller.allow_test_evidence = allow_test_evidence
        try:
            return self.caller.admit(adm.inner, adm.detail)
        finally:
            self.caller.allow_test_evidence = True
